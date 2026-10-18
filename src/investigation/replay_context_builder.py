import argparse
import json
import math
from datetime import timedelta
from statistics import fmean

from google.cloud import firestore

from investigation.cloud_context_builder import (
    CloudInvestigationContextBuilder,
    SENSOR_COLUMNS,
)


class ReplayInvestigationContextBuilder(CloudInvestigationContextBuilder):
    """Reconstruct the evidence available at a replay's first alert."""

    def __init__(self, simulation_id):
        super().__init__()
        self.simulation_id = str(simulation_id).strip()

        if not self.simulation_id or "/" in self.simulation_id:
            raise ValueError("Invalid simulation ID.")

        self.firestore = firestore.Client(
            project=self.project,
            database="(default)",
        )
        self.session = self.firestore.collection("simulations").document(
            self.simulation_id
        )

    def build_context(self, event_id):
        event_id = str(event_id).strip()
        if not event_id or "/" in event_id:
            raise ValueError("Invalid replay event ID.")

        event_snapshot = (
            self.session.collection("events")
            .document(event_id)
            .get(timeout=30)
        )
        if not event_snapshot.exists:
            raise ValueError("Replay event was not found.")

        saved_event = event_snapshot.to_dict()
        if saved_event.get("simulation_id") != self.simulation_id:
            raise ValueError("Event belongs to a different simulation.")

        trigger_id = saved_event["trigger_prediction_id"]
        prediction_snapshot = (
            self.session.collection("predictions")
            .document(trigger_id)
            .get(timeout=30)
        )
        if not prediction_snapshot.exists:
            raise ValueError("Trigger prediction was not found.")

        prediction = prediction_snapshot.to_dict()
        machine_id = saved_event["machine_id"]
        start = prediction["start_time"]
        cutoff = prediction["end_time"]

        if prediction["machine_id"] != machine_id:
            raise ValueError("Trigger prediction machine mismatch.")

        if (
            cutoff != saved_event["investigation_cutoff"]
            or cutoff != saved_event["first_detected_at"]
            or start != saved_event["start_time"]
        ):
            raise ValueError("Trigger prediction and event boundaries differ.")

        if (
            prediction["window_minutes"] != 30
            or prediction["window_step_minutes"] != 5
            or cutoff - start != timedelta(minutes=29)
        ):
            raise ValueError("Unexpected replay window configuration.")

        probability = float(prediction["fault_probability"])
        threshold = float(prediction["threshold"])

        if not (
            math.isfinite(probability)
            and math.isfinite(threshold)
            and 0 <= probability <= 1
            and 0 <= threshold <= 1
            and prediction["predicted_fault"] == 1
            and probability >= threshold
        ):
            raise ValueError("Trigger prediction is not a valid flagged window.")

        last_sequence = int(prediction["sequence_id"])
        if last_sequence < 29 or trigger_id != f"{last_sequence:04d}":
            raise ValueError("Invalid trigger sequence.")

        # Read exactly the trigger window's 30 documents.
        references = [
            self.session.collection("readings").document(f"{index:04d}")
            for index in range(last_sequence - 29, last_sequence + 1)
        ]
        snapshots = list(
            self.firestore.get_all(references, timeout=30)
        )
        if len(snapshots) != 30 or any(
            not snapshot.exists for snapshot in snapshots
        ):
            raise ValueError("The trigger window is missing readings.")

        rows = sorted(
            [snapshot.to_dict() for snapshot in snapshots],
            key=lambda row: row["timestamp"],
        )

        for offset, row in enumerate(rows):
            if row["machine_id"] != machine_id:
                raise ValueError("Reading machine mismatch.")

            if row["sequence_id"] != last_sequence - 29 + offset:
                raise ValueError("Unexpected reading sequence.")

            if row["timestamp"] != start + timedelta(minutes=offset):
                raise ValueError("Missing or unexpected reading timestamp.")

            for sensor in SENSOR_COLUMNS:
                value = row.get(sensor)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError(f"Invalid reading for {sensor}.")

        summary = {
            "sensor_readings_found": 30,
            "distinct_sensor_timestamps": 30,
            "first_sensor_timestamp": start,
            "last_sensor_timestamp": cutoff,
        }
        for sensor in SENSOR_COLUMNS:
            values = [float(row[sensor]) for row in rows]
            summary.update({
                f"min_{sensor}": min(values),
                f"max_{sensor}": max(values),
                f"mean_{sensor}": fmean(values),
                f"valid_{sensor}_count": len(values),
            })

        # Globally distinguish this event from other replay sessions.
        report_event_id = f"{self.simulation_id}__{event_id}"

        # Construct a first-alert snapshot. Do not copy the completed
        # event's later count, maximum probability, or closing time.
        event = {
            "event_id": report_event_id,
            "machine_id": machine_id,
            "source_run_id": self.simulation_id,
            "model_version": prediction["model_version"],
            "partition": "test",
            "start_time": start,
            "end_time": cutoff,
            "first_detected_at": cutoff,
            "flagged_window_count": 1,
            "max_fault_probability": probability,
            "mean_fault_probability": probability,
            "threshold": threshold,
            "window_minutes": prediction["window_minutes"],
            "window_step_minutes": prediction["window_step_minutes"],
            "grouping_version": "replay_first_alert_v1",
            "created_at": saved_event["created_at"],
        }

        context = self.build_context_for_event(
            event,
            sensor_summary=summary,
        )

        # Preserve the existing synthetic-report prompt condition.
        context["analysis_mode"] = "synthetic_historical_event_review"
        context["replay_scope"] = {
            "simulation_id": self.simulation_id,
            "replay_event_id": event_id,
            "trigger_prediction_id": trigger_id,
            "review_scope": "first_alert_snapshot",
            "data_origin": "prerecorded_synthetic_sensor_data",
            "note": (
                "This report reconstructs the first replay alert. "
                "Later readings, predictions, and event updates are excluded. "
                "Scenario times are simulated; they do not establish "
                "that a real incident occurred."
            ),
        }
        context["sensor_summary_scope"]["source"] = (
            "Firestore replay readings"
        )
        context["sensor_summary_scope"]["note"] = (
            "Calculated from exactly 30 replay readings in the trigger "
            "window. Min/max/mean values are not trends. Sensor units, "
            "operating limits, and subsystem mappings are not established."
        )
        context["machine_logs_scope"]["records_found"] = (
            context["machine_logs_scope"]["records_returned"]
        )

        return context

    def close(self):
        try:
            self.firestore.close()
        finally:
            super().close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation-id", required=True)
    parser.add_argument("--event-id", default="event_0001")
    args = parser.parse_args()

    builder = ReplayInvestigationContextBuilder(args.simulation_id)
    try:
        context = builder.build_context(args.event_id)
        print(json.dumps(context, indent=2, allow_nan=False))
    finally:
        builder.close()


if __name__ == "__main__":
    main()