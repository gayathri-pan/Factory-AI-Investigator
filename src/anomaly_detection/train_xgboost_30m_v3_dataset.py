
from pathlib import Path
import json

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    precision_recall_curve,
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

# Separate V3 model directory
MODEL_DIR = (
    ROOT / "models" / "xgboost_experiment_30m_v3_dataset"
)

# Separate V3 results directory
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

METRICS_PATH = (
    RESULTS_DIR / "validation_metrics_v3_dataset.json"
)

PREDICTIONS_PATH = (
    RESULTS_DIR / "validation_predictions_v3_dataset.csv.gz"
)

SENSOR_FEATURES = [
    "temperature",
    "vibration",
    "pressure",
    "rpm",
    "power_consumption",
]

RANDOM_STATE = 42



# ---------------------------------------------------------
# 2. HELPER: VALIDATION METRICS
# ---------------------------------------------------------

def calculate_metrics(y_true, probabilities, threshold):
    predictions = (probabilities >= threshold).astype(int)

    cm = confusion_matrix(
        y_true,
        predictions,
        labels=[0, 1],
    )

    return {
        "threshold": float(threshold),
        "precision": float(
            precision_score(
                y_true, predictions, zero_division=0
            )
        ),
        "recall": float(
            recall_score(
                y_true, predictions, zero_division=0
            )
        ),
        "f1": float(
            f1_score(
                y_true, predictions, zero_division=0
            )
        ),
        "average_precision": float(
            average_precision_score(y_true, probabilities)
        ),
        "true_negatives": int(cm[0, 0]),
        "false_positives": int(cm[0, 1]),
        "false_negatives": int(cm[1, 0]),
        "true_positives": int(cm[1, 1]),
        "flagged_windows": int(predictions.sum()),
    }


# ---------------------------------------------------------
# 3. MAIN TRAINING PIPELINE
# ---------------------------------------------------------

def main():

    print("=" * 65)
    print("XGBOOST BINARY BASELINE")
    print("=" * 65)

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Preprocessed dataset not found: {DATA_PATH}"
        )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading preprocessed feature data...")

    data = pd.read_csv(
        DATA_PATH,
        compression="gzip",
    )

    print(f"Dataset shape: {data.shape}")

    required_columns = {
        "partition",
        "sensor_fault",
        "machine_id",
        "start_time",
        "end_time",
    }

    missing = required_columns - set(data.columns)

    if missing:
        raise ValueError(
            f"Required columns are missing: {sorted(missing)}"
        )

    # Select the 96 engineered numeric sensor features.
    # Exclude scenario IDs, scenario types, timestamps,
    # target labels, and other metadata.

    # Select the 96 engineered V3 sensor features.
    # Exclude scenario IDs, types, timestamps and target labels.

    feature_columns = [
        column
        for column in data.columns
        if (
            any(
                column.startswith(f"{sensor}_")
                for sensor in SENSOR_FEATURES
            )
            or column == "max_longest_equal_run_any_sensor"
        )
    ]

    if len(feature_columns) != 96:
        raise ValueError(
            f"Expected 96 numeric features, "
            f"but found {len(feature_columns)}."
        )

    partitions = {
        name: data.loc[data["partition"] == name]
        for name in ["train", "validation"]
    }

    train = partitions["train"]
    validation = partitions["validation"]

    if train.empty or validation.empty:
        raise ValueError(
            "Training or validation partition is empty."
        )

    X_train = train[feature_columns]
    y_train = train["sensor_fault"].astype(int)

    X_val = validation[feature_columns]
    y_val = validation["sensor_fault"].astype(int)

    # Make sure the features are valid for training.
    if not np.isfinite(X_train.to_numpy()).all():
        raise ValueError(
            "Training features contain NaN or infinite values."
        )

    if not np.isfinite(X_val.to_numpy()).all():
        raise ValueError(
            "Validation features contain NaN or infinite values."
        )

    if y_train.nunique() < 2 or y_val.nunique() < 2:
        raise ValueError(
            "Both classes must be present in training and validation."
        )

    positive_count = int((y_train == 1).sum())
    negative_count = int((y_train == 0).sum())

    scale_pos_weight = negative_count / positive_count

    print("\n=== TRAINING DATA ===")
    print(f"Training windows: {len(train):,}")
    print(f"Positive fault windows: {positive_count:,}")
    print(f"Negative windows: {negative_count:,}")
    print(f"Positive rate: {y_train.mean():.4%}")
    print(f"scale_pos_weight: {scale_pos_weight:.2f}")

    print("\n=== VALIDATION DATA ===")
    print(f"Validation windows: {len(validation):,}")
    print(f"Positive fault windows: {int(y_val.sum()):,}")
    print(f"Negative windows: {int((y_val == 0).sum()):,}")

    print(f"\nNumber of input features: {len(feature_columns)}")
    print("Excluded: target labels and scenario metadata.")

    # -----------------------------------------------------
    # 4. TRAIN XGBOOST
    # -----------------------------------------------------

    print("\nTraining XGBoost...")

    model = XGBClassifier(
        objective="binary:logistic",
        eval_metric="aucpr",
        n_estimators=1200,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=5,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        scale_pos_weight=scale_pos_weight,
        tree_method="hist",
        n_jobs=-1,
        random_state=RANDOM_STATE,
        early_stopping_rounds=50,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=100,
    )

    print("\nTraining finished.")
    print(f"Best boosting iteration: {model.best_iteration}")
    print(f"Best validation PR-AUC metric: {model.best_score}")

    # -----------------------------------------------------
    # 5. SELECT THE DECISION THRESHOLD ON VALIDATION
    # -----------------------------------------------------

    print("\nSelecting decision threshold from validation data...")

    val_probabilities = model.predict_proba(X_val)[:, 1]

    precision_curve, recall_curve, thresholds = (
        precision_recall_curve(y_val, val_probabilities)
    )

    # Precision and recall have one more element than thresholds.
    precision_curve = precision_curve[:-1]
    recall_curve = recall_curve[:-1]

    denominators = precision_curve + recall_curve

    f1_candidates = np.divide(
        2 * precision_curve * recall_curve,
        denominators,
        out=np.zeros_like(denominators),
        where=denominators > 0,
    )

    if len(thresholds) == 0:
        raise RuntimeError(
            "Unable to select a threshold from validation predictions."
        )

    best_index = int(np.argmax(f1_candidates))
    best_threshold = float(thresholds[best_index])

    # Save validation results using the chosen threshold.
    metrics = calculate_metrics(
        y_val,
        val_probabilities,
        best_threshold,
    )

    metrics["best_iteration"] = int(model.best_iteration)
    metrics["validation_windows"] = int(len(validation))
    metrics["training_windows"] = int(len(train))
    metrics["training_positive_count"] = positive_count
    metrics["training_negative_count"] = negative_count
    metrics["scale_pos_weight"] = float(scale_pos_weight)
    metrics["input_feature_count"] = len(feature_columns)
    metrics["threshold_selection_method"] = (
        "Maximum F1 on validation precision-recall curve"
    )

    print("\n=== VALIDATION RESULTS ===")
    print(f"Selected threshold: {best_threshold:.6f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall: {metrics['recall']:.4f}")
    print(f"F1 score: {metrics['f1']:.4f}")
    print(
        "Average precision: "
        f"{metrics['average_precision']:.4f}"
    )

    print("\nConfusion matrix counts:")
    print(f"True negatives:  {metrics['true_negatives']:,}")
    print(f"False positives: {metrics['false_positives']:,}")
    print(f"False negatives: {metrics['false_negatives']:,}")
    print(f"True positives:  {metrics['true_positives']:,}")
    print(f"Flagged windows: {metrics['flagged_windows']:,}")

    # -----------------------------------------------------
    # 6. SAVE MODEL AND EXPERIMENT ARTIFACTS
    # -----------------------------------------------------

    print("\nSaving model and experiment artifacts...")

    model.save_model(MODEL_PATH)

    FEATURES_PATH.write_text(
        json.dumps(feature_columns, indent=2),
        encoding="utf-8",
    )

    THRESHOLD_PATH.write_text(
        json.dumps(
            {
                "threshold": best_threshold,
                "selection_partition": "validation",
                "selection_metric": "F1",
                "model": "xgboost_binary_v3_dataset",
                "positive_class": 1,
                "negative_class": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    METRICS_PATH.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    validation_predictions = validation[
        ["machine_id", "start_time", "end_time", "sensor_fault"]
    ].copy()

    validation_predictions["fault_probability"] = (
        val_probabilities
    )

    validation_predictions["predicted_fault"] = (
        val_probabilities >= best_threshold
    ).astype(int)

    validation_predictions.to_csv(
        PREDICTIONS_PATH,
        index=False,
        compression="gzip",
    )

    # Save feature importance for interpretation.
    importance = pd.DataFrame({
        "feature": feature_columns,
        "importance": model.feature_importances_,
    }).sort_values(
        "importance",
        ascending=False,
    )

    importance.to_csv(
        RESULTS_DIR / "feature_importance.csv",
        index=False,
    )

    print("\n=== SAVED FILES ===")
    print(f"Model: {MODEL_PATH}")
    print(f"Feature list: {FEATURES_PATH}")
    print(f"Threshold: {THRESHOLD_PATH}")
    print(f"Metrics: {METRICS_PATH}")
    print(f"Validation predictions: {PREDICTIONS_PATH}")
    print(f"Feature importance: {RESULTS_DIR / 'feature_importance.csv'}")

    print("\nTest data was not used for training or threshold selection.")
    print("\nTRAINING PIPELINE COMPLETE")


if __name__ == "__main__":
    main()
