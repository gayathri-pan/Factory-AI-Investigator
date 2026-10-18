import json
import os
import uuid
from datetime import datetime, timezone
from google.cloud import bigquery
import hashlib
import re
from google.api_core.exceptions import Conflict

PROMPT_VERSION = "investigation_markdown_v3"

def make_investigation_id(
    event_id,
    model_name,
    knowledge_base_version,
    prompt_version=PROMPT_VERSION,
):
    """Stable identity for one event and investigation configuration."""
    identity = {
        "event_id": event_id,
        "model_name": model_name,
        "knowledge_base_version": knowledge_base_version,
        "prompt_version": prompt_version,
        "review_scope": "first_alert_snapshot_v1",
    }
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return f"inv_{hashlib.sha256(encoded).hexdigest()}"

class InvestigationReportStore:
    def __init__(self):
        self.project = os.getenv(
            "GOOGLE_CLOUD_PROJECT",
            "project-e64210d0-f317-4050-833",
        )
        self.location = os.getenv("BIGQUERY_LOCATION", "asia-south1")
        self.table = (
            f"{self.project}.factory_ai_investigator."
            "investigation_reports"
        )
        self.client = bigquery.Client(
            project=self.project,
            location=self.location,
        )

    def save_completed(self, package, report, model_name, investigation_id=None,):

        """Call only after generate_report() returns successfully."""
        if package.get("evidence_gate", {}).get("sufficient") is not True:
            raise ValueError("Cannot save a completed report without gate approval.")

        if not isinstance(report, str) or not report.strip():
            raise ValueError("Cannot save an empty report.")

        event = package["anomaly_event"]
        if investigation_id is None:
            # Preserve existing local callers' behavior.
            investigation_id = f"inv_{uuid.uuid4().hex}"

        if not re.fullmatch(r"inv_[0-9a-f]{32,64}", investigation_id):
            raise ValueError("Invalid investigation ID.")

        existing = self.get_report(investigation_id)
        if existing is not None:
            self._check_identity(
                existing, package, model_name
            )
            return investigation_id
        created_at = datetime.now(timezone.utc)

        validation = {
            "validator_version": "markdown_structure_v1",
            "generation_finished_normally": True,
            "required_sections_present_and_nonempty": True,
            "section_order_checked": True,
            "technical_evidence_ids_checked": True,
            "factual_correctness_independently_verified": False,
            "note": (
                "Recorded after the report generator returned successfully. "
                "These checks do not establish factual or causal correctness."
            ),
        }

        values = [
            ("investigation_id", "STRING", investigation_id),
            ("event_id", "STRING", event["event_id"]),
            ("machine_id", "STRING", event["machine_id"]),
            ("source_run_id", "STRING", event["source_run_id"]),
            ("created_at", "TIMESTAMP", created_at),
            ("model_name", "STRING", model_name),
            (
                "knowledge_base_version",
                "STRING",
                package["knowledge_base_version"],
            ),
            ("prompt_version", "STRING", PROMPT_VERSION),
            ("report_markdown", "STRING", report),
            (
                "context_json",
                "STRING",
                json.dumps(package, allow_nan=False),
            ),
            (
                "gate_json",
                "STRING",
                json.dumps(package["evidence_gate"], allow_nan=False),
            ),
            (
                "validation_json",
                "STRING",
                json.dumps(validation, allow_nan=False),
            ),
        ]

        sql = f"""
        INSERT INTO `{self.table}` (
            investigation_id,
            event_id,
            machine_id,
            source_run_id,
            created_at,
            status,
            model_name,
            knowledge_base_version,
            prompt_version,
            report_markdown,
            investigation_context,
            evidence_gate,
            validation_results
        )
        SELECT
            @investigation_id,
            @event_id,
            @machine_id,
            @source_run_id,
            @created_at,
            'completed',
            @model_name,
            @knowledge_base_version,
            @prompt_version,
            @report_markdown,
            PARSE_JSON(@context_json),
            PARSE_JSON(@gate_json),
            PARSE_JSON(@validation_json)
        FROM (SELECT 1 AS placeholder)
        WHERE NOT EXISTS (
            SELECT 1
            FROM `{self.table}`
            WHERE investigation_id = @investigation_id
        )
        """

        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(name, kind, value)
                for name, kind, value in values
            ]
        )

        job_identity = (
            f"{self.table}|{investigation_id}|insert_sql_v2"
        ).encode("utf-8")
        job_id = (
            "save_report_"
            + hashlib.sha256(job_identity).hexdigest()
        )

        try:
            job = self.client.query(
                sql,
                job_config=config,
                job_id=job_id,
                job_retry=None,
                location=self.location,
            )
        except Conflict:
            # Another attempt already submitted this same save.
            job = self.client.get_job(
                job_id,
                project=self.project,
                location=self.location,
            )

        job.result(job_retry=None)

        saved = self.get_report(investigation_id)
        if saved is None:
            raise RuntimeError(
                "Save job completed but the report was not found."
            )

        self._check_identity(saved, package, model_name)
        return investigation_id
    
    @staticmethod
    def _check_identity(saved, package, model_name):
        event = package["anomaly_event"]

        expected = {
            "event_id": event["event_id"],
            "machine_id": event["machine_id"],
            "source_run_id": event["source_run_id"],
            "model_name": model_name,
            "knowledge_base_version": package["knowledge_base_version"],
            "prompt_version": PROMPT_VERSION,
            "status": "completed",
        }

        for field, value in expected.items():
            if saved.get(field) != value:
                raise RuntimeError(
                    f"Existing report identity mismatch: {field}"
                )

        if not saved.get("report_markdown", "").strip():
            raise RuntimeError("Existing completed report is empty.")

    def get_report(self, investigation_id):
        sql = f"""
        SELECT
            investigation_id,
            event_id,
            machine_id,
            source_run_id,
            created_at,
            status,
            model_name,
            knowledge_base_version,
            prompt_version,
            report_markdown,
            TO_JSON_STRING(investigation_context) AS context_json,
            TO_JSON_STRING(evidence_gate) AS gate_json,
            TO_JSON_STRING(validation_results) AS validation_json
        FROM `{self.table}`
        WHERE investigation_id = @investigation_id
        LIMIT 2
        """

        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "investigation_id", "STRING", investigation_id
                )
            ]
        )

        rows = list(
            self.client.query(
                sql,
                job_config=config,
                location=self.location,
            ).result()
        )

        if not rows:
            return None
        if len(rows) > 1:
            raise RuntimeError("Duplicate investigation ID found.")

        result = dict(rows[0].items())
        result["created_at"] = result["created_at"].isoformat()

        for source, target in (
            ("context_json", "investigation_context"),
            ("gate_json", "evidence_gate"),
            ("validation_json", "validation_results"),
        ):
            result[target] = json.loads(result.pop(source))

        return result

    def close(self):
        self.client.close()