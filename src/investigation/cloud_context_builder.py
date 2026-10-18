import argparse
import json
import os
from datetime import date, datetime

from google.cloud import bigquery


PROJECT_ID = "project-e64210d0-f317-4050-833"
DATASET_ID = "factory_ai_investigator"

SENSOR_COLUMNS = (
    "temperature",
    "vibration",
    "pressure",
    "rpm",
    "power_consumption",
)


def json_ready(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


class CloudInvestigationContextBuilder:
    """Read event-specific investigation context from BigQuery."""

    def __init__(self):
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
        self.location = os.getenv("BIGQUERY_LOCATION", "asia-south1")
        self.dataset = f"{self.project}.{DATASET_ID}"
        self.client = bigquery.Client(
            project=self.project,
            location=self.location,
        )

    def _query(self, sql, parameters):
        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(name, kind, value)
                for name, kind, value in parameters
            ]
        )
        rows = self.client.query(
            sql,
            job_config=config,
            location=self.location,
        ).result()
        return [dict(row.items()) for row in rows]

    def build_context(self, event_id):
        event_id = str(event_id).strip()
        if not event_id:
            raise ValueError("event_id cannot be empty.")

        events = self._query(
            f"""
            SELECT *
            FROM `{self.dataset}.anomaly_events`
            WHERE event_id = @event_id
            LIMIT 2
            """,
            [("event_id", "STRING", event_id)],
        )

        if len(events) != 1:
            raise ValueError(
                f"Expected one event; found {len(events)} for {event_id}."
            )

        event = events[0]
        return self.build_context_for_event(events[0])

    def build_context_for_event(self, event, sensor_summary=None):
        """Build supporting context for a supplied event snapshot."""
        machine_id = event["machine_id"]
        machine_id = event["machine_id"]
        start = event["start_time"]
        end = event["end_time"]

        if start is None or end is None or end < start:
            raise ValueError("Invalid event time boundaries.")

        machine_parameters = [("machine_id", "STRING", machine_id)]
        window_parameters = machine_parameters + [
            ("start_time", "TIMESTAMP", start),
            ("end_time", "TIMESTAMP", end),
        ]

        machines = self._query(
            f"""
            SELECT *
            FROM `{self.dataset}.factory_machines`
            WHERE machine_id = @machine_id
            LIMIT 2
            """,
            machine_parameters,
        )

        if len(machines) > 1:
            raise ValueError(f"Duplicate machine metadata for {machine_id}.")

        machine = (
            {**machines[0], "metadata_available": True}
            if machines
            else {"machine_id": machine_id, "metadata_available": False}
        )

        # These fields have no observation timestamp in the source table.
        # Do not present them as verified status at the historical event.
        snapshot_fields = {
            field: machine.pop(field)
            for field in ("status", "operating_hours")
            if field in machine
        }

        aggregates = ",\n".join(
            f"MIN({column}) AS min_{column}, "
            f"MAX({column}) AS max_{column}, "
            f"AVG({column}) AS mean_{column}, "
            f"COUNT({column}) AS valid_{column}_count"
            for column in SENSOR_COLUMNS
        )

        if sensor_summary is None:
            sensor_summary = self._query(
                f"""
                SELECT
                    COUNT(*) AS sensor_readings_found,
                    COUNT(DISTINCT timestamp) AS distinct_sensor_timestamps,
                    MIN(timestamp) AS first_sensor_timestamp,
                    MAX(timestamp) AS last_sensor_timestamp,
                    {aggregates}
                FROM `{self.dataset}.sensors`
                WHERE machine_id = @machine_id
                  AND timestamp BETWEEN @start_time AND @end_time
                """,
                window_parameters,
            )[0]

        logs = self._query(
            f"""
            SELECT *
            FROM `{self.dataset}.machine_logs`
            WHERE machine_id = @machine_id
              AND timestamp BETWEEN @start_time AND @end_time
            ORDER BY timestamp, component, message
            LIMIT 201
            """,
            window_parameters,
        )

        # DATE-only records cannot establish ordering within the event day.
        history_parameters = machine_parameters + [
            ("event_date", "DATE", start.date()),
        ]

        maintenance = self._query(
            f"""
            SELECT *
            FROM `{self.dataset}.maintenance_history`
            WHERE machine_id = @machine_id
              AND date < @event_date
            ORDER BY date DESC, maintenance_id
            LIMIT 21
            """,
            history_parameters,
        )

        incidents = self._query(
            f"""
            SELECT *
            FROM `{self.dataset}.historical_incidents`
            WHERE machine_id = @machine_id
              AND date < @event_date
            ORDER BY date DESC, incident_id
            LIMIT 21
            """,
            history_parameters,
        )

        context = {
            "machine": machine,
            "machine_metadata_scope": {
                "untimed_snapshot_fields_excluded": snapshot_fields,
                "note": (
                    "Status and operating hours have no observation timestamp "
                    "and are not established as values at the selected event."
                ),
            },
            "anomaly_event": event,
            "sensor_summary": sensor_summary,
            "sensor_summary_scope": {
                "machine_id": machine_id,
                "start_time": start,
                "end_time": end,
                "note": (
                    "Min/max/mean values are summary statistics, not trends. "
                    "Sensor units and operating limits are not supplied "
                    "by the sensors table."
                ),
            },
            "machine_logs": logs[:200],
            "machine_logs_scope": {
                "machine_id": machine_id,
                "start_time": start,
                "end_time": end,
                "records_returned": min(len(logs), 200),
                "truncated": len(logs) > 200,
                "outside_window_searched": False,
            },
            "maintenance_history": maintenance[:20],
            "historical_incidents": incidents[:20],
            "history_scope": {
                "date_exclusive_upper_bound": start.date(),
                "timezone": "UTC",
                "maintenance_limit": 20,
                "incident_limit": 20,
                "maintenance_truncated": len(maintenance) > 20,
                "incidents_truncated": len(incidents) > 20,
                "note": (
                    "Only earlier calendar dates are included. Record dates "
                    "do not independently prove when their contents became "
                    "available; no recorded-at timestamps exist in these tables."
                ),
            },
            "investigation_cutoff": end,
            "analysis_mode": "synthetic_historical_event_review",
        }

        return json_ready(context)

    def close(self):
        self.client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    args = parser.parse_args()

    builder = CloudInvestigationContextBuilder()
    try:
        context = builder.build_context(args.event_id)
        print(json.dumps(context, indent=2, allow_nan=False))
    finally:
        builder.close()


if __name__ == "__main__":
    main()