
"""Score the prepared XGBoost V3 feature dataset on Google Cloud.

Reads feature data and model artifacts from Cloud Storage.
Scores all prepared windows in batches.
Publishes the completed prediction table to BigQuery only after
the full scoring and staging load succeed.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import bigquery
from google.cloud import storage
from xgboost import XGBClassifier


PROJECT_ID = os.getenv(
    "GOOGLE_CLOUD_PROJECT",
    "project-e64210d0-f317-4050-833",
)
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
BUCKET_NAME = (
    "factory-ai-investigator-data-e64210d0-f317-4050-833"
)

FEATURES_BLOB = (
    "inference-input/xgboost_window_features_v3_dataset.csv.gz"
)
MODEL_BLOB = (
    "model-artifacts/xgboost_binary_v3_dataset.json"
)
COLUMNS_BLOB = (
    "model-artifacts/feature_columns_v3_dataset.json"
)
THRESHOLD_BLOB = (
    "model-artifacts/validation_threshold_v3_dataset.json"
)

DATASET_ID = "factory_ai_investigator"
OUTPUT_TABLE = (
    f"{PROJECT_ID}.{DATASET_ID}."
    "xgboost_v3_window_predictions"
)

MODEL_VERSION = "xgboost_30m_v3_dataset"
WINDOW_MINUTES = 30
WINDOW_STEP_MINUTES = 5
CHUNK_SIZE = 10_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


OUTPUT_SCHEMA = [
    bigquery.SchemaField("machine_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("start_time", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("end_time", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("partition", "STRING", mode="NULLABLE"),
    bigquery.SchemaField(
        "fault_probability", "FLOAT64", mode="REQUIRED"
    ),
    bigquery.SchemaField("predicted_fault", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("threshold", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("window_minutes", "INT64", mode="REQUIRED"),
    bigquery.SchemaField(
        "window_step_minutes", "INT64", mode="REQUIRED"
    ),
    bigquery.SchemaField("model_version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("scored_at", "TIMESTAMP", mode="REQUIRED"),
]


def download_blob(
    storage_client: storage.Client,
    blob_name: str,
    destination: Path,
) -> None:
    """Download one object from Cloud Storage."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)

    if not blob.exists():
        raise FileNotFoundError(
            f"Cloud Storage object not found: "
            f"gs://{BUCKET_NAME}/{blob_name}"
        )

    logger.info("Downloading gs://%s/%s", BUCKET_NAME, blob_name)
    blob.download_to_filename(str(destination))
    logger.info("Downloaded %s bytes", destination.stat().st_size)


def main() -> None:
    run_id = uuid.uuid4().hex[:12]
    scored_at = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    staging_table = (
        f"{PROJECT_ID}.{DATASET_ID}."
        f"xgb_v3_predictions_staging_{run_id}"
    )

    logger.info("Starting XGBoost batch inference")
    logger.info("Project: %s", PROJECT_ID)
    logger.info("Region: %s", LOCATION)
    logger.info("Run ID: %s", run_id)
    logger.info("Final table: %s", OUTPUT_TABLE)

    storage_client = storage.Client(project=PROJECT_ID)
    bq_client = bigquery.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        features_path = temp_path / "features.csv.gz"
        model_path = temp_path / "model.json"
        columns_path = temp_path / "feature_columns.json"
        threshold_path = temp_path / "threshold.json"
        predictions_path = temp_path / "predictions.ndjson"

        # Download the existing inputs. Do not retrain or regenerate features.
        download_blob(storage_client, FEATURES_BLOB, features_path)
        download_blob(storage_client, MODEL_BLOB, model_path)
        download_blob(storage_client, COLUMNS_BLOB, columns_path)
        download_blob(storage_client, THRESHOLD_BLOB, threshold_path)

        feature_columns = json.loads(
            columns_path.read_text(encoding="utf-8")
        )
        threshold_config = json.loads(
            threshold_path.read_text(encoding="utf-8")
        )
        threshold = float(threshold_config["threshold"])

        if len(feature_columns) != 96:
            raise ValueError(
                f"Expected 96 model features, "
                f"found {len(feature_columns)}"
            )

        if len(set(feature_columns)) != 96:
            raise ValueError("Feature list contains duplicates")

        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Invalid threshold: {threshold}")

        model = XGBClassifier()
        model.load_model(str(model_path))

        logger.info("Loaded model with 96 features")
        logger.info("Frozen threshold: %.6f", threshold)

        total_rows = 0
        total_flagged = 0

        # Stream the compressed CSV in chunks to limit memory use.
        chunks = pd.read_csv(
            features_path,
            compression="gzip",
            chunksize=CHUNK_SIZE,
            low_memory=False,
        )

        with predictions_path.open(
            "w", encoding="utf-8"
        ) as output_file:
            for chunk_number, chunk in enumerate(chunks, start=1):
                required_metadata = [
                    "machine_id",
                    "start_time",
                    "end_time",
                    "partition",
                ]
                missing_metadata = [
                    col for col in required_metadata
                    if col not in chunk.columns
                ]
                missing_features = [
                    col for col in feature_columns
                    if col not in chunk.columns
                ]

                if missing_metadata or missing_features:
                    raise ValueError(
                        f"Chunk {chunk_number} has missing columns. "
                        f"Metadata: {missing_metadata}; "
                        f"features: {missing_features}"
                    )

                # Only the 96 trained features go into the model.
                # Labels, scenario data and metadata are excluded.
                X = chunk[feature_columns].apply(
                    pd.to_numeric, errors="raise"
                )

                values = X.to_numpy(dtype=np.float64)
                if not np.isfinite(values).all():
                    raise ValueError(
                        f"Non-finite feature values in chunk "
                        f"{chunk_number}"
                    )

                probabilities = model.predict_proba(X)[:, 1]
                predictions = (
                    probabilities >= threshold
                ).astype(np.int64)

                # Normalize timestamps to UTC for BigQuery TIMESTAMP fields.
                start_times = pd.to_datetime(
                    chunk["start_time"], utc=True, errors="raise"
                )
                end_times = pd.to_datetime(
                    chunk["end_time"], utc=True, errors="raise"
                )

                if start_times.isna().any() or end_times.isna().any():
                    raise ValueError(
                        f"Missing timestamps in chunk {chunk_number}"
                    )

                for i in range(len(chunk)):
                    record = {
                        "machine_id": str(chunk["machine_id"].iloc[i]),
                        "start_time": start_times.iloc[i].isoformat(),
                        "end_time": end_times.iloc[i].isoformat(),
                        "partition": (
                            None
                            if pd.isna(chunk["partition"].iloc[i])
                            else str(chunk["partition"].iloc[i])
                        ),
                        "fault_probability": float(probabilities[i]),
                        "predicted_fault": int(predictions[i]),
                        "threshold": threshold,
                        "window_minutes": WINDOW_MINUTES,
                        "window_step_minutes": WINDOW_STEP_MINUTES,
                        "model_version": MODEL_VERSION,
                        "run_id": run_id,
                        "scored_at": scored_at,
                    }
                    output_file.write(json.dumps(record) + "\n")

                total_rows += len(chunk)
                total_flagged += int(predictions.sum())

                logger.info(
                    "Chunk %d complete: %d rows; "
                    "%d flagged so far",
                    chunk_number,
                    len(chunk),
                    total_flagged,
                )

        if total_rows == 0:
            raise RuntimeError("Feature dataset contains no rows")

        logger.info(
            "Scoring complete: %d rows, %d flagged",
            total_rows,
            total_flagged,
        )

        # Load the completed output into a unique staging table first.
        # The existing final table is not changed if scoring/loading fails.
        job_config = bigquery.LoadJobConfig(
            schema=OUTPUT_SCHEMA,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        logger.info("Loading predictions into staging table")
        with predictions_path.open("rb") as file_obj:
            load_job = bq_client.load_table_from_file(
                file_obj,
                staging_table,
                rewind=True,
                size=predictions_path.stat().st_size,
                job_config=job_config,
                location=LOCATION,
            )
        load_job.result()

        staged = bq_client.get_table(staging_table)
        if staged.num_rows != total_rows:
            raise RuntimeError(
                f"Row-count mismatch: scored {total_rows}, "
                f"staged {staged.num_rows}"
            )

        # Publish only after the complete staging load succeeds.
        logger.info("Publishing completed predictions table")
        copy_config = bigquery.CopyJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )
        copy_job = bq_client.copy_table(
            staging_table,
            OUTPUT_TABLE,
            job_config=copy_config,
            location=LOCATION,
        )
        copy_job.result()

        final_table = bq_client.get_table(OUTPUT_TABLE)
        logger.info("Inference completed successfully")
        logger.info("Published table: %s", OUTPUT_TABLE)
        logger.info("Rows in final table: %d", final_table.num_rows)
        logger.info("Flagged windows: %d", total_flagged)

        bq_client.delete_table(staging_table, not_found_ok=True)


if __name__ == "__main__":
    main()
