import logging
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from google.cloud import firestore
from google.api_core.exceptions import BadRequest
from investigation.cloud_context_builder import CloudInvestigationContextBuilder
from pydantic import BaseModel, Field

from investigation.cloud_investigator import CloudFactoryInvestigator
from investigation.evidence_gate import EvidenceGate
from investigation.replay_context_builder import (
    ReplayInvestigationContextBuilder,
)
from investigation.report_generator import InvestigationReportGenerator
from investigation.report_store import (
    InvestigationReportStore,
    make_investigation_id,
)
from rag.cloud_vector_store import CloudFactoryVectorStore
from rag.retriever import FactoryRetriever


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# One investigation at a time per process.
process_lock = threading.Lock()
LEASE_MINUTES = 20


class InvestigationRequest(BaseModel):
    simulation_id: str = Field(pattern=r"^sim_[0-9a-f]{32}$")
    event_id: str = Field(pattern=r"^event_[0-9]+$")


@asynccontextmanager
async def lifespan(app):
    vector_store = CloudFactoryVectorStore()
    try:
        app.state.vector_store = vector_store
        app.state.retriever = FactoryRetriever(
            top_k=3,
            vector_store=vector_store,
        )
        app.state.gate = EvidenceGate(min_relevance_score=0.70)
        app.state.generator = InvestigationReportGenerator()
        yield
    finally:
        vector_store.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ready",
        "knowledge_base_version":
            app.state.vector_store.knowledge_base_version,
    }


@firestore.transactional
def claim(transaction, ref, owner, proposed_report_id):
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists:
        raise ValueError("Replay event does not exist.")

    data = snapshot.to_dict()
    status = data.get("investigation_status", "not_requested")

    if status == "report_ready":
        if not data.get("investigation_id"):
            raise ValueError("Ready event has no report ID.")
        return "ready", data["investigation_id"]

    if status in ("blocked", "needs_review"):
        return status, None

    now = datetime.now(timezone.utc)
    lease_until = data.get("investigation_lease_until")

    if status == "investigating":
        # A legacy local process has no lease. Do not take over blindly.
        if lease_until is None or lease_until > now:
            return "busy", None

    # Preserve the investigation identity across task deliveries.
    report_id = data.get("investigation_request_id", proposed_report_id)
    if report_id != proposed_report_id:
        return "configuration_mismatch", None

    transaction.update(ref, {
        "investigation_status": "investigating",
        "investigation_stage": "checking_saved_report",
        "investigation_attempt_id": owner,
        "investigation_request_id": report_id,
        "investigation_lease_until":
            now + timedelta(minutes=LEASE_MINUTES),
        "investigation_updated_at": firestore.SERVER_TIMESTAMP,
    })
    return "claimed", report_id


@firestore.transactional
def progress(transaction, ref, owner, status, stage, fields):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    now = datetime.now(timezone.utc)

    lease_until = data.get("investigation_lease_until")
    if (
        data.get("investigation_attempt_id") != owner
        or data.get("investigation_status") != "investigating"
        or lease_until is None
        or lease_until <= now
    ):
        raise RuntimeError("Investigation lease lost or expired.")

    transaction.update(ref, {
        **fields,
        "investigation_status": status,
        "investigation_stage": stage,
        "investigation_updated_at": firestore.SERVER_TIMESTAMP,
        "investigation_lease_until": (
            now + timedelta(minutes=LEASE_MINUTES)
            if status == "investigating"
            else now
        ),
    })


def verify_saved(saved, context):
    if saved is None:
        raise RuntimeError("Saved report was not found.")

    event = context["anomaly_event"]
    for field in ("event_id", "machine_id", "source_run_id"):
        if saved.get(field) != event[field]:
            raise RuntimeError(f"Report identity mismatch: {field}")

    if (
        saved.get("status") != "completed"
        or not saved.get("report_markdown", "").strip()
    ):
        raise RuntimeError("Saved report is incomplete.")

    saved_context = saved.get("investigation_context") or {}
    if (
        saved_context.get("investigation_cutoff")
        != context["investigation_cutoff"]
    ):
        raise RuntimeError("Report investigation cutoff mismatch.")


@app.post("/tasks/investigate")
def investigate(request: InvestigationRequest):
    if not process_lock.acquire(blocking=False):
        raise HTTPException(503, "Worker is processing another investigation.")

    builder = None
    store = None
    claimed = False
    owner = uuid.uuid4().hex
    stage = "initializing"

    try:
        builder = ReplayInvestigationContextBuilder(
            request.simulation_id
        )
        store = InvestigationReportStore()
        ref = builder.session.collection("events").document(
            request.event_id
        )
        report_event_id = (
            f"{request.simulation_id}__{request.event_id}"
        )
        generator = app.state.generator

        proposed_id = make_investigation_id(
            event_id=report_event_id,
            model_name=generator.model_name,
            knowledge_base_version=(
                app.state.vector_store.knowledge_base_version
            ),
        )

        outcome, report_id = claim(
            builder.firestore.transaction(),
            ref,
            owner,
            proposed_id,
        )

        if outcome == "busy":
            raise HTTPException(503, "Another investigation owns this event.")

        if outcome in ("blocked", "needs_review"):
            return {"status": outcome}

        if outcome == "configuration_mismatch":
            # Do not silently change the model/prompt for a retry.
            return {
                "status": "needs_review",
                "reason": "Investigation configuration changed.",
            }

        claimed = outcome == "claimed"

        def update(status, next_stage, **fields):
            nonlocal stage
            progress(
                builder.firestore.transaction(),
                ref,
                owner,
                status,
                next_stage,
                fields,
            )
            stage = next_stage
            logger.info("%s: %s", report_event_id, next_stage)

        context = builder.build_context(request.event_id)
        saved = store.get_report(report_id)

        if outcome == "ready":
            verify_saved(saved, context)
            return {
                "status": "report_ready",
                "investigation_id": report_id,
                "reused": True,
            }

        if saved is None:
            update("investigating", "retrieving_and_assessing")

            investigator = CloudFactoryInvestigator(
                context_builder=builder,
                retriever=app.state.retriever,
                evidence_gate=app.state.gate,
            )
            package = investigator.assess_event(request.event_id)
            gate = package["evidence_gate"]

            if gate["sufficient"] is not True:
                # Current gate may also return false for an API error.
                update(
                    "blocked",
                    "gate_not_passed",
                    investigation_reason=str(gate.get("reason", "")),
                    investigation_missing_information=gate.get(
                        "missing_information", []
                    ),
                )
                return {"status": "blocked"}

            update("investigating", "generating_report")
            report = generator.generate_report(package)

            update("investigating", "saving_report")
            store.save_completed(
                package=package,
                report=report,
                model_name=generator.model_name,
                investigation_id=report_id,
            )
            saved = store.get_report(report_id)
        else:
            # Recovery after BigQuery saved but Firestore was not updated.
            store._check_identity(
                saved,
                {
                    **context,
                    "knowledge_base_version":
                        app.state.vector_store.knowledge_base_version,
                },
                generator.model_name,
            )

        verify_saved(saved, context)

        update(
            "report_ready",
            "completed",
            investigation_id=report_id,
            investigation_report_event_id=report_event_id,
            investigation_report_source="bigquery",
            investigation_error_type=None,
            investigation_reason="",
            investigation_finished_at=firestore.SERVER_TIMESTAMP,
        )
        return {
            "status": "report_ready",
            "investigation_id": report_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Investigation request failed at %s", stage)

        if claimed:
            try:
                # Preserve request ID so a later delivery can recover
                # the same BigQuery report/save job.
                progress(
                    builder.firestore.transaction(),
                    ref,
                    owner,
                    "failed",
                    stage,
                    {"investigation_error_type": type(exc).__name__},
                )
            except Exception:
                logger.exception("Could not publish failure status.")

        raise HTTPException(503, "Investigation failed; inspect worker logs.")
    finally:
        try:
            if store is not None:
                store.close()
        finally:
            try:
                if builder is not None:
                    builder.close()
            finally:
                process_lock.release()


class HistoricalInvestigationRequest(BaseModel):
    event_id: str = Field(pattern=r'^evt_[0-9a-f]{64}$')
    dispatch_generation: int = Field(ge=1)


@firestore.transactional
def claim_historical(transaction, ref, owner, proposed_id, generation):
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists:
        raise ValueError('Historical investigation request does not exist.')
    data = snapshot.to_dict() or {}
    if data.get('dispatch_generation') != generation:
        return 'superseded', None
    status = data.get('investigation_status', 'queued')
    if status == 'report_ready':
        if not data.get('investigation_id'):
            raise ValueError('Ready investigation has no report ID.')
        return 'ready', data['investigation_id']
    if status in ('blocked', 'needs_review'):
        return status, None
    now = datetime.now(timezone.utc)
    lease = data.get('investigation_lease_until')
    if status == 'investigating' and (lease is None or lease > now):
        return 'busy', None
    report_id = data.get('investigation_request_id', proposed_id)
    if report_id != proposed_id:
        transaction.update(ref, {
            'investigation_status':'needs_review',
            'investigation_stage':'configuration_mismatch',
            'investigation_reason':'The investigation model, prompt or knowledge-base configuration changed.',
            'investigation_updated_at':firestore.SERVER_TIMESTAMP,
        })
        return 'needs_review', None
    transaction.update(ref, {
        'investigation_status':'investigating',
        'investigation_stage':'checking_saved_report',
        'investigation_attempt_id':owner,
        'investigation_request_id':report_id,
        'investigation_lease_until':now + timedelta(minutes=LEASE_MINUTES),
        'investigation_updated_at':firestore.SERVER_TIMESTAMP,
        'investigation_error_type':None,
    })
    return 'claimed', report_id


@app.post('/tasks/investigate-historical')
def investigate_historical(request: HistoricalInvestigationRequest):
    if not process_lock.acquire(blocking=False):
        raise HTTPException(503, 'Worker is processing another investigation.')
    builder = None
    store = None
    history_db = None
    claimed = False
    owner = uuid.uuid4().hex
    stage = 'initializing'
    try:
        builder = CloudInvestigationContextBuilder()
        history_db = firestore.Client(project=builder.project, database='(default)')
        store = InvestigationReportStore()
        ref = history_db.collection('historical_investigations').document(request.event_id)
        generator = app.state.generator
        kb = app.state.vector_store.knowledge_base_version
        # Namespace the full historical-event review separately from replay
        # first-alert snapshots. The saved event_id remains the actual BQ ID.
        proposed_id = make_investigation_id(
            event_id='historical_full_event_v1:' + request.event_id,
            model_name=generator.model_name,
            knowledge_base_version=kb,
        )
        outcome, report_id = claim_historical(history_db.transaction(), ref,
            owner, proposed_id, request.dispatch_generation)
        if outcome == 'busy':
            raise HTTPException(503, 'Another attempt owns this investigation.')
        if outcome in ('superseded', 'blocked', 'needs_review'):
            return {'status':outcome}
        claimed = outcome == 'claimed'

        def update(status, next_stage, **fields):
            nonlocal stage
            progress(history_db.transaction(), ref, owner, status, next_stage, fields)
            stage = next_stage
            logger.info('historical %s: %s', request.event_id, next_stage)

        context = builder.build_context(request.event_id)
        context['machine_logs_scope']['records_found'] = context['machine_logs_scope']['records_returned']
        saved = store.get_report(report_id)
        if outcome == 'ready':
            verify_saved(saved, context)
            return {'status':'report_ready', 'investigation_id':report_id, 'reused':True}

        if saved is None:
            update('investigating', 'retrieving_and_assessing')
            investigator = CloudFactoryInvestigator(context_builder=builder,
                retriever=app.state.retriever, evidence_gate=app.state.gate)
            package = investigator.assess_event(request.event_id)
            package['machine_logs_scope']['records_found'] = package['machine_logs_scope']['records_returned']
            package['review_scope'] = 'full_historical_event'
            gate = package['evidence_gate']
            # Publish actual accepted passages even if the gate blocks a report.
            update('investigating', 'retrieving_and_assessing',
                evidence_collected=True,
                accepted_evidence=package.get('technical_evidence', []),
                evidence_gate=gate,
                investigation_query=package.get('investigation_query', ''),
            )
            if gate.get('sufficient') is not True:
                update('blocked', 'gate_not_passed',
                    investigation_reason=str(gate.get('reason', 'Evidence gate did not pass.')),
                    investigation_missing_information=gate.get('missing_information', []),
                    investigation_finished_at=firestore.SERVER_TIMESTAMP,
                )
                return {'status':'blocked'}

            update('investigating', 'generating_report')
            report_text = generator.generate_report(package)
            update('investigating', 'saving_report')
            store.save_completed(package=package, report=report_text,
                model_name=generator.model_name, investigation_id=report_id)
            saved = store.get_report(report_id)
        else:
            store._check_identity(saved, {**context, 'knowledge_base_version':kb}, generator.model_name)

        verify_saved(saved, context)
        saved_context = saved.get('investigation_context') or {}
        update('report_ready', 'completed',
            investigation_id=report_id,
            investigation_report_event_id=request.event_id,
            investigation_report_source='bigquery',
            investigation_error_type=None,
            investigation_reason='',
            investigation_finished_at=firestore.SERVER_TIMESTAMP,
            evidence_collected=True,
            accepted_evidence=saved_context.get('technical_evidence', []),
            evidence_gate=saved_context.get('evidence_gate', {}),
            investigation_query=saved_context.get('investigation_query', ''),
        )
        return {'status':'report_ready', 'investigation_id':report_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Historical investigation failed at %s', stage)
        permanent = isinstance(exc, (BadRequest, TypeError, ValueError))
        if claimed:
            try:
                progress(history_db.transaction(), ref, owner,
                    'needs_review' if permanent else 'failed', stage, {
                        'investigation_error_type':type(exc).__name__,
                        'investigation_reason':(
                            'The investigation encountered a processing error. Operator review is required.'
                            if permanent else 'The last attempt failed. A further retry has not been confirmed.'
                        ),
                    })
            except Exception:
                logger.exception('Could not update historical failure status.')
        if permanent and claimed:
            # A broken SQL/schema/interface should not repeatedly spend Gemini
            # calls. Preserve state and acknowledge the task for operator review.
            return {'status':'needs_review'}
        raise HTTPException(503, 'Historical investigation failed; inspect worker logs.')
    finally:
        try:
            if store is not None:
                store.close()
        finally:
            try:
                if builder is not None:
                    builder.close()
            finally:
                try:
                    if history_db is not None:
                        history_db.close()
                finally:
                    process_lock.release()
