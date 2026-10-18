import argparse
import uuid

from google.cloud import firestore

from investigation.cloud_investigator import CloudFactoryInvestigator
from investigation.evidence_gate import EvidenceGate
from investigation.replay_context_builder import (
    ReplayInvestigationContextBuilder,
)
from investigation.report_generator import InvestigationReportGenerator
from investigation.report_store import InvestigationReportStore
from rag.cloud_vector_store import CloudFactoryVectorStore
from rag.retriever import FactoryRetriever


@firestore.transactional
def claim_event(transaction, event_ref, attempt_id):
    snapshot = event_ref.get(transaction=transaction)
    if not snapshot.exists:
        raise ValueError("Replay event was not found.")

    event = snapshot.to_dict()
    status = event.get("investigation_status", "not_requested")

    # Do not silently rerun completed, failed, or interrupted work.
    if status != "not_requested":
        return False, status

    transaction.update(event_ref, {
        "investigation_status": "investigating",
        "investigation_stage": "starting",
        "investigation_attempt_id": attempt_id,
        "investigation_started_at": firestore.SERVER_TIMESTAMP,
        "investigation_updated_at": firestore.SERVER_TIMESTAMP,
    })
    return True, "investigating"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation-id", required=True)
    parser.add_argument("--event-id", default="event_0001")
    parser.add_argument(
        "--existing-report-id",
        help="Verify and link an existing report without calling Gemini.",
    )
    args = parser.parse_args()

    builder = ReplayInvestigationContextBuilder(args.simulation_id)
    vector_store = None
    store = None
    claimed = False
    report_id = args.existing_report_id
    save_started = False

    if not args.event_id.strip() or "/" in args.event_id:
        builder.close()
        raise ValueError("Invalid event ID.")

    event_ref = builder.session.collection("events").document(
        args.event_id
    )
    expected_event_id = (
        f"{args.simulation_id}__{args.event_id}"
    )

    def update_status(status, stage, **fields):
        event_ref.update({
            "investigation_status": status,
            "investigation_stage": stage,
            "investigation_updated_at": firestore.SERVER_TIMESTAMP,
            **fields,
        }, timeout=30)
        print(f"INVESTIGATION | {status} | {stage}", flush=True)

    try:
        claimed, current_status = claim_event(
            builder.firestore.transaction(),
            event_ref,
            uuid.uuid4().hex,
        )

        if not claimed:
            print(
                f"No work started: investigation status is "
                f"{current_status}.",
                flush=True,
            )
            return

        store = InvestigationReportStore()
        generated_report = None

        if report_id:
            update_status("investigating", "verifying_existing_report")
        else:
            update_status("investigating", "loading_knowledge_base")
            vector_store = CloudFactoryVectorStore()

            investigator = CloudFactoryInvestigator(
                context_builder=builder,
                retriever=FactoryRetriever(
                    top_k=3,
                    vector_store=vector_store,
                ),
                evidence_gate=EvidenceGate(min_relevance_score=0.70),
            )

            update_status("investigating", "retrieving_and_assessing")
            package = investigator.assess_event(args.event_id)
            gate = package["evidence_gate"]

            if gate["sufficient"] is not True:
                # The current gate may also return false on an API error.
                # Therefore do not label every false result
                # as proven evidence insufficiency.
                update_status(
                    "blocked",
                    "gate_not_passed",
                    investigation_reason=str(gate.get("reason", "")),
                    investigation_missing_information=gate.get(
                        "missing_information", []
                    ),
                    investigation_finished_at=firestore.SERVER_TIMESTAMP,
                )
                return

            update_status("investigating", "generating_report")
            generator = InvestigationReportGenerator()
            generated_report = generator.generate_report(package)

            update_status("investigating", "saving_report")
            save_started = True
            report_id = store.save_completed(
                package=package,
                report=generated_report,
                model_name=generator.model_name,
            )

        update_status(
            "investigating",
            "verifying_saved_report",
            investigation_candidate_report_id=report_id,
        )
        saved = store.get_report(report_id)
        if saved is None:
            raise RuntimeError("Saved report could not be retrieved.")

        event = event_ref.get(timeout=30).to_dict()

        if saved["event_id"] != expected_event_id:
            raise RuntimeError("Report event ID does not match this replay.")

        if saved["machine_id"] != event["machine_id"]:
            raise RuntimeError("Report machine ID does not match.")

        if saved["source_run_id"] != args.simulation_id:
            raise RuntimeError("Report source run does not match.")

        if saved["status"] != "completed":
            raise RuntimeError("The saved report is not completed.")

        if not saved.get("report_markdown", "").strip():
            raise RuntimeError("The saved report is empty.")

        if (
            generated_report is not None
            and saved["report_markdown"] != generated_report
        ):
            raise RuntimeError("Report read-back text differs.")

        update_status(
            "report_ready",
            "completed",
            investigation_id=report_id,
            investigation_report_event_id=expected_event_id,
            investigation_report_source="bigquery",
            investigation_finished_at=firestore.SERVER_TIMESTAMP,
        )

        print(f"Report linked: {report_id}", flush=True)
        print(
            "Report ready means generation and storage completed; "
            "it does not establish a confirmed root cause.",
            flush=True,
        )

    except (Exception, KeyboardInterrupt) as exc:
        if claimed:
            # A BigQuery save might have succeeded even when the
            # client did not receive its response. Avoid automatic retries.
            status = (
                "needs_review"
                if save_started or report_id
                else "failed"
            )
            try:
                update_status(
                    status,
                    "stopped",
                    investigation_error_type=type(exc).__name__,
                    investigation_candidate_report_id=report_id,
                )
            except Exception as status_error:
                print(
                    "Could not update Firestore failure status:",
                    type(status_error).__name__,
                    flush=True,
                )
        raise
    finally:
        if store is not None:
            store.close()
        if vector_store is not None:
            vector_store.close()
        builder.close()


if __name__ == "__main__":
    main()