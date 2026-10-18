from pathlib import Path
import json

import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    balanced_accuracy_score,
)


# ---------------------------------------------------------
# 1. PATHS AND CONFIGURATION
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

# V3 preprocessed feature dataset
DATA_PATH = (
    ROOT
    / "data"
    / "xgboost_experiment_30m_v3_dataset"
    / "processed"
    / "xgboost_window_features_v3_dataset.csv.gz"
)

# V3 ground-truth scenario labels
SCENARIO_PATH = (
    ROOT
    / "data"
    / "yearly_experiment_v3"
    / "raw"
    / "scenario_labels.csv"
)

# V3 trained model and configuration
MODEL_DIR = (
    ROOT / "models" / "xgboost_experiment_30m_v3_dataset"
)

RESULTS_DIR = (
    ROOT
    / "data"
    / "xgboost_experiment_30m_v3_dataset"
    / "results"
)

MODEL_PATH = MODEL_DIR / "xgboost_binary_v3_dataset.json"

FEATURES_PATH = (
    MODEL_DIR / "feature_columns_v3_dataset.json"
)

THRESHOLD_PATH = (
    MODEL_DIR / "validation_threshold_v3_dataset.json"
)

# V3 test evaluation outputs
METRICS_PATH = RESULTS_DIR / "test_metrics_v3_dataset.json"

PREDICTIONS_PATH = (
    RESULTS_DIR / "test_predictions_v3_dataset.csv.gz"
)

SCENARIO_RESULTS_PATH = (
    RESULTS_DIR / "test_scenario_detection_v3_dataset.csv"
)


def main():
    print("=" * 65)
    print("XGBOOST V3 TEST EVALUATION")
    print("=" * 65)

    # Check that all required input artifacts exist before loading them.
    required_paths = [
        DATA_PATH,
        SCENARIO_PATH,
        MODEL_PATH,
        FEATURES_PATH,
        THRESHOLD_PATH,
    ]
    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        missing_text = "\n".join(f"- {path}" for path in missing_paths)
        raise FileNotFoundError(
            "Required V3 evaluation files were not found:\n" + missing_text
        )

    # Load the already-trained V3 model and its frozen validation threshold.
    model = XGBClassifier()
    model.load_model(MODEL_PATH)

    feature_columns = json.loads(
        FEATURES_PATH.read_text(encoding="utf-8")
    )
    threshold_config = json.loads(
        THRESHOLD_PATH.read_text(encoding="utf-8")
    )
    threshold = float(threshold_config["threshold"])

    # Read the preprocessed data, then evaluate only the held-out test partition.
    data = pd.read_csv(
        DATA_PATH,
        compression="gzip",
        low_memory=False,
    )

    test = data[data["partition"] == "test"].copy()

    if test.empty:
        raise ValueError("No test windows were found in the V3 dataset.")

    missing_features = [
        column for column in feature_columns if column not in test.columns
    ]
    if missing_features:
        raise ValueError(
            "Required model features are missing from the test dataset: "
            f"{missing_features}"
        )

    X_test = test[feature_columns]
    y_test = test["sensor_fault"].astype(int).to_numpy()

    if not np.isfinite(X_test.to_numpy()).all():
        raise ValueError("Test features contain invalid values.")

    probabilities = model.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= threshold).astype(int)

    # Window-level metrics.
    tn, fp, fn, tp = confusion_matrix(
        y_test,
        predictions,
        labels=[0, 1],
    ).ravel()

    metrics = {
        "partition": "test",
        "threshold": threshold,
        "threshold_source": "validation",
        "test_windows": int(len(test)),
        "positive_windows": int(y_test.sum()),
        "negative_windows": int((y_test == 0).sum()),
        "precision": float(
            precision_score(y_test, predictions, zero_division=0)
        ),
        "recall": float(
            recall_score(y_test, predictions, zero_division=0)
        ),
        "f1": float(
            f1_score(y_test, predictions, zero_division=0)
        ),
        "average_precision": float(
            average_precision_score(y_test, probabilities)
        ),
        "balanced_accuracy": float(
            balanced_accuracy_score(y_test, predictions)
        ),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "flagged_windows": int(predictions.sum()),
    }

    print("\n=== V3 TEST WINDOW METRICS ===")
    for key, value in metrics.items():
        print(f"{key}: {value}")

    # Save test predictions for scenario-level analysis.
    prediction_columns = [
        "machine_id",
        "start_time",
        "end_time",
        "sensor_fault",
        "scenario_ids",
        "scenario_types",
    ]
    missing_prediction_columns = [
        column for column in prediction_columns if column not in test.columns
    ]
    if missing_prediction_columns:
        raise ValueError(
            "Required metadata columns are missing from test data: "
            f"{missing_prediction_columns}"
        )

    test_predictions = test[prediction_columns].copy()
    test_predictions["fault_probability"] = probabilities
    test_predictions["predicted_fault"] = predictions

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    test_predictions.to_csv(
        PREDICTIONS_PATH,
        index=False,
        compression="gzip",
    )

    METRICS_PATH.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    # Scenario-level detection:
    # A scenario is detected if at least one predicted-anomaly window
    # overlaps the scenario's machine and time interval.
    labels = pd.read_csv(
        SCENARIO_PATH,
        low_memory=False,
    )

    labels["planned_partition"] = (
        labels["planned_partition"]
        .astype(str)
        .str.strip()
        .str.lower()
    )
    labels["start_time"] = pd.to_datetime(labels["start_time"])
    labels["end_time"] = pd.to_datetime(labels["end_time"])

    test_scenarios = labels[
        labels["planned_partition"] == "test"
    ].copy()

    test_predictions["start_time"] = pd.to_datetime(
        test_predictions["start_time"]
    )
    test_predictions["end_time"] = pd.to_datetime(
        test_predictions["end_time"]
    )

    scenario_rows = []

    for scenario in test_scenarios.itertuples(index=False):
        overlapping = test_predictions[
            (test_predictions["machine_id"] == scenario.machine_id)
            & (test_predictions["start_time"] <= scenario.end_time)
            & (test_predictions["end_time"] >= scenario.start_time)
            & (test_predictions["predicted_fault"] == 1)
        ]

        scenario_rows.append({
            "scenario_id": scenario.scenario_id,
            "machine_id": scenario.machine_id,
            "scenario_type": scenario.scenario_type,
            "detected": not overlapping.empty,
            "detected_windows": len(overlapping),
        })

    scenario_results = pd.DataFrame(scenario_rows)

    scenario_results.to_csv(
        SCENARIO_RESULTS_PATH,
        index=False,
    )

    print("\n=== V3 TEST SCENARIO DETECTION ===")
    if scenario_results.empty:
        print("No test scenarios were found in the V3 scenario labels.")
    else:
        print(
            scenario_results.groupby("scenario_type")
            .agg(
                total_scenarios=("scenario_id", "count"),
                detected_scenarios=("detected", "sum"),
                flagged_windows=("detected_windows", "sum"),
            )
            .to_string()
        )

    fault_types = {
        "gradual_fault",
        "intermittent_fault",
        "sensor_anomaly",
    }

    sensor_scenarios = scenario_results[
        scenario_results["scenario_type"].isin(fault_types)
    ]

    print("\n=== V3 OVERALL SENSOR-FAULT SCENARIO DETECTION ===")
    print(
        f"Detected: {int(sensor_scenarios['detected'].sum())} "
        f"/ {len(sensor_scenarios)}"
    )

    print(f"\nSaved test metrics: {METRICS_PATH}")
    print(f"Saved test predictions: {PREDICTIONS_PATH}")
    print(f"Saved scenario results: {SCENARIO_RESULTS_PATH}")
    print(
        "\nTest results are for evaluation only. "
        "The trained model and validation-selected threshold were not changed."
    )


if __name__ == "__main__":
    main()
