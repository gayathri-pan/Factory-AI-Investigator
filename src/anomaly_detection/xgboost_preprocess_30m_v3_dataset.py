from pathlib import Path
import numpy as np
import pandas as pd

# ---------------------------------------------------------
# 1. PATHS AND CONFIGURATION
# ---------------------------------------------------------


ROOT = Path(__file__).resolve().parents[2]

# V3 synthetic dataset
RAW_DIR = (
    ROOT / "data" / "yearly_experiment_v3" / "raw"
)

# Separate V3 preprocessing output
OUTPUT_DIR = (
    ROOT
    / "data"
    / "xgboost_experiment_30m_v3_dataset"
    / "processed"
)

SENSOR_PATH = RAW_DIR / "sensors.csv"
SCENARIO_PATH = RAW_DIR / "scenario_labels.csv"

OUTPUT_PATH = (
    OUTPUT_DIR / "xgboost_window_features_v3_dataset.csv.gz"
)

WINDOW_SIZE = 30
WINDOW_STEP = 5

TRAIN_RATIO = 0.70
VALIDATION_RATIO = 0.15

SENSOR_FEATURES = [
    "temperature",
    "vibration",
    "pressure",
    "rpm",
    "power_consumption",
]

# These are the scenarios the sensor-fault classifier will learn.
SENSOR_FAULT_TYPES = {
    "gradual_fault",
    "intermittent_fault",
    "sensor_anomaly",
}


# ---------------------------------------------------------
# 2. CREATE FEATURES FOR ONE MACHINE/PARTITION
# ---------------------------------------------------------

def create_window_features(
    machine_data,
    machine_scenarios,
    partition,
):
    """
    Create one feature row for every 30-minute window.

    Windows advance by 5 minutes and never cross a
    train/validation/test boundary.
    """

    machine_data = machine_data.reset_index(drop=True)

    n_rows = len(machine_data)

    if n_rows < WINDOW_SIZE:
        return pd.DataFrame()

    # The first window ends at index 59.
    end_positions = np.arange(
        WINDOW_SIZE - 1,
        n_rows,
        WINDOW_STEP,
    )

    start_positions = end_positions - WINDOW_SIZE + 1

    timestamps = machine_data["timestamp"]

    windows = pd.DataFrame({
        "machine_id": machine_data["machine_id"].iloc[
            start_positions
        ].to_numpy(),

        "start_time": timestamps.iloc[
            start_positions
        ].to_numpy(),

        "end_time": timestamps.iloc[
            end_positions
        ].to_numpy(),

        "partition": partition,
    })

    # -----------------------------------------------------
    # 3. CALCULATE SENSOR FEATURES
    # -----------------------------------------------------
    longest_runs_by_sensor = []

    for feature in SENSOR_FEATURES:

        values = machine_data[feature].to_numpy(
            dtype=np.float64
        )

        series = pd.Series(values)

        rolling = series.rolling(
            window=WINDOW_SIZE,
            min_periods=WINDOW_SIZE,
        )

        rolling_mean = rolling.mean().to_numpy()
        rolling_std = rolling.std(ddof=0).to_numpy()
        rolling_min = rolling.min().to_numpy()
        rolling_max = rolling.max().to_numpy()

        first_values = values[start_positions]
        last_values = values[end_positions]

        prefix = feature

        windows[f"{prefix}_mean"] = (
            rolling_mean[end_positions]
        )

        windows[f"{prefix}_std"] = (
            rolling_std[end_positions]
        )

        windows[f"{prefix}_min"] = (
            rolling_min[end_positions]
        )

        windows[f"{prefix}_max"] = (
            rolling_max[end_positions]
        )

        windows[f"{prefix}_range"] = (
            rolling_max[end_positions]
            - rolling_min[end_positions]
        )

        windows[f"{prefix}_first"] = first_values
        windows[f"{prefix}_last"] = last_values

        windows[f"{prefix}_delta"] = (
            last_values - first_values
        )

        # Average absolute change between consecutive readings.
        # A 30-reading window contains 29 consecutive changes.
        absolute_changes = pd.Series(
            np.abs(np.diff(values))
        )

        rolling_change = absolute_changes.rolling(
            window=WINDOW_SIZE - 1,
            min_periods=WINDOW_SIZE - 1,
        ).mean().to_numpy()

        windows[f"{prefix}_mean_abs_change"] = (
            rolling_change[end_positions - 1]
        )


        # -------------------------------------------------
        # V2 FEATURES: SHORT-DURATION SENSOR ANOMALIES
        # -------------------------------------------------

        # 1. Median: robust measure of the typical reading.
        rolling_median = rolling.median().to_numpy()

        windows[f"{prefix}_median"] = (
            rolling_median[end_positions]
        )

        # Split each 30-reading window into six 5-reading
        # subwindows to capture short-duration changes.
        subwindow_size = 5

        subwindow_means = []
        subwindow_stds = []
        subwindow_ranges = []

        for sub_start in range(0, WINDOW_SIZE, subwindow_size):
            sub_stop = min(
                sub_start + subwindow_size,
                WINDOW_SIZE,
            )

            subwindow_values = np.column_stack([
                values[start_positions + offset]
                for offset in range(sub_start, sub_stop)
            ])

            subwindow_means.append(
                subwindow_values.mean(axis=1)
            )

            subwindow_stds.append(
                subwindow_values.std(axis=1)
            )

            subwindow_ranges.append(
                subwindow_values.max(axis=1)
                - subwindow_values.min(axis=1)
            )

        subwindow_mean_matrix = np.column_stack(
            subwindow_means
        )

        subwindow_std_matrix = np.column_stack(
            subwindow_stds
        )

        subwindow_range_matrix = np.column_stack(
            subwindow_ranges
        )

        # 2. Lowest and highest 5-reading segment means.
        windows[f"{prefix}_subwindow_mean_min"] = (
            subwindow_mean_matrix.min(axis=1)
        )

        windows[f"{prefix}_subwindow_mean_max"] = (
            subwindow_mean_matrix.max(axis=1)
        )

        windows[f"{prefix}_subwindow_mean_range"] = (
            subwindow_mean_matrix.max(axis=1)
            - subwindow_mean_matrix.min(axis=1)
        )

        # 3. Variability inside short segments.
        windows[f"{prefix}_subwindow_std_min"] = (
            subwindow_std_matrix.min(axis=1)
        )

        windows[f"{prefix}_subwindow_std_max"] = (
            subwindow_std_matrix.max(axis=1)
        )

        windows[f"{prefix}_subwindow_range_max"] = (
            subwindow_range_matrix.max(axis=1)
        )

        # 4. Largest change between adjacent segment means.
        windows[f"{prefix}_max_abs_subwindow_mean_change"] = (
            np.abs(
                np.diff(subwindow_mean_matrix, axis=1)
            ).max(axis=1)
        )

        # 5. Find the longest consecutive run of identical
        # readings anywhere inside each 30-reading window.
        # Unlike the old counter, this does not depend on
        # alignment with five-reading segment boundaries.

        window_values = np.column_stack([
            values[start_positions + offset]
            for offset in range(WINDOW_SIZE)
        ])

        equal_adjacent = (
            window_values[:, 1:] == window_values[:, :-1]
        )

        current_run = np.ones(
            len(windows),
            dtype=np.int16,
        )

        longest_run = current_run.copy()

        for j in range(equal_adjacent.shape[1]):
            current_run = np.where(
                equal_adjacent[:, j],
                current_run + 1,
                1,
            )

            longest_run = np.maximum(
                longest_run,
                current_run,
            )

        windows[f"{prefix}_longest_equal_run"] = longest_run

        # Retain this sensor's result for the shared feature.
        longest_runs_by_sensor.append(longest_run)

        # 6. Fraction of consecutive readings that are equal.
        # This can help identify sensors that temporarily stick.
        equal_adjacent = (
            np.diff(values) == 0
        ).astype(np.float64)

        rolling_equal_fraction = pd.Series(
            equal_adjacent
        ).rolling(
            window=WINDOW_SIZE - 1,
            min_periods=WINDOW_SIZE - 1,
        ).mean().to_numpy()

        windows[f"{prefix}_zero_change_fraction"] = (
            rolling_equal_fraction[end_positions - 1]
        )

    # Shared feature: longest identical-reading run
    # across all five sensors for each time window.
    windows["max_longest_equal_run_any_sensor"] = (
        np.maximum.reduce(longest_runs_by_sensor)
        )
    # -----------------------------------------------------
    # 4. GENERATE TARGET LABELS FROM SCENARIO INTERVALS
    # -----------------------------------------------------

    # These fields are for labelling/evaluation only.
    # They will NOT be used as XGBoost input features.
    scenario_ids = [
        [] for _ in range(len(windows))
    ]

    scenario_types = [
        [] for _ in range(len(windows))
    ]

    sensor_fault = np.zeros(
        len(windows),
        dtype=np.int8,
    )

    windows["contains_any_scenario"] = False

    for scenario in machine_scenarios.itertuples(
        index=False
    ):

        # A window overlaps the scenario if their time intervals
        # intersect. Both interval endpoints are included.
        overlaps = (
            (windows["start_time"] <= scenario.end_time)
            & (windows["end_time"] >= scenario.start_time)
        ).to_numpy()

        overlapping_positions = np.flatnonzero(overlaps)

        if len(overlapping_positions) == 0:
            continue

        windows.loc[
            overlaps, "contains_any_scenario"
        ] = True

        for position in overlapping_positions:
            scenario_ids[position].append(
                scenario.scenario_id
            )

            scenario_types[position].append(
                scenario.scenario_type
            )

        # Only sensor-related fault scenarios are positive.
        # Warning-only scenarios do not count as sensor faults.
        if scenario.scenario_type in SENSOR_FAULT_TYPES:
            sensor_fault[overlaps] = 1

    windows["sensor_fault"] = sensor_fault

    windows["scenario_ids"] = [
        ";".join(sorted(set(ids)))
        for ids in scenario_ids
    ]

    windows["scenario_types"] = [
        ";".join(sorted(set(types)))
        for types in scenario_types
    ]

    return windows


# ---------------------------------------------------------
# 5. MAIN PREPROCESSING PIPELINE
# ---------------------------------------------------------

def main():

    print("=" * 65)
    print("XGBOOST WINDOW FEATURE PREPROCESSING")
    print("=" * 65)

    if not SENSOR_PATH.exists():
        raise FileNotFoundError(
            f"Sensor data not found: {SENSOR_PATH}"
        )

    if not SCENARIO_PATH.exists():
        raise FileNotFoundError(
            f"Scenario labels not found: {SCENARIO_PATH}"
        )

    print("\nLoading sensor readings...")

    sensors = pd.read_csv(
        SENSOR_PATH,
        parse_dates=["timestamp"],
    )

    scenarios = pd.read_csv(
        SCENARIO_PATH,
        parse_dates=["start_time", "end_time"],
    )

    # Normalize values used by the pipeline.
    sensors["machine_id"] = (
        sensors["machine_id"].astype(str).str.strip()
    )

    scenarios["machine_id"] = (
        scenarios["machine_id"].astype(str).str.strip()
    )

    scenarios["scenario_type"] = (
        scenarios["scenario_type"].astype(str).str.strip()
    )

    scenarios["planned_partition"] = (
        scenarios["planned_partition"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    missing_columns = (
        {"timestamp", "machine_id"} | set(SENSOR_FEATURES)
    ) - set(sensors.columns)

    if missing_columns:
        raise ValueError(
            f"Missing sensor columns: {sorted(missing_columns)}"
        )

    # Verify that the required sensor values are numeric.
    for feature in SENSOR_FEATURES:
        sensors[feature] = pd.to_numeric(
            sensors[feature],
            errors="coerce",
        )

    if sensors[SENSOR_FEATURES].isna().any().any():
        raise ValueError(
            "Sensor features contain missing or non-numeric values. "
            "Inspect and handle them before training."
        )

    if sensors["timestamp"].isna().any():
        raise ValueError("Some timestamps could not be parsed.")

    duplicate_count = sensors.duplicated(
        ["machine_id", "timestamp"]
    ).sum()

    if duplicate_count:
        raise ValueError(
            f"Found {duplicate_count} duplicate machine/timestamp "
            "records. Resolve duplicates before creating windows."
        )

    sensors = sensors.sort_values(
        ["machine_id", "timestamp"]
    ).reset_index(drop=True)

    print(f"Sensor rows: {len(sensors):,}")
    print(f"Machines: {sensors['machine_id'].nunique()}")
    print(f"Scenario labels: {len(scenarios)}")

    print("\nScenario counts by planned partition:")
    print(
        scenarios["planned_partition"].value_counts().to_string()
    )

    all_windows = []

    # -----------------------------------------------------
    # 6. SPLIT EACH MACHINE CHRONOLOGICALLY
    # -----------------------------------------------------

    for machine_id, machine_data in sensors.groupby(
        "machine_id",
        sort=True,
    ):

        machine_data = machine_data.reset_index(drop=True)

        n_rows = len(machine_data)

        train_end = int(n_rows * TRAIN_RATIO)

        validation_end = int(
            n_rows * (TRAIN_RATIO + VALIDATION_RATIO)
        )

        partitions = {
            "train": machine_data.iloc[:train_end],
            "validation": machine_data.iloc[
                train_end:validation_end
            ],
            "test": machine_data.iloc[validation_end:],
        }

        print(f"\nProcessing {machine_id}: {n_rows:,} readings")

        for partition, partition_data in partitions.items():

            partition_scenarios = scenarios[
                (scenarios["machine_id"] == machine_id)
                & (
                    scenarios["planned_partition"]
                    == partition
                )
            ].copy()

            features = create_window_features(
                machine_data=partition_data,
                machine_scenarios=partition_scenarios,
                partition=partition,
            )

            if features.empty:
                print(
                    f"  {partition}: no complete windows"
                )
                continue

            positive = int(features["sensor_fault"].sum())

            print(
                f"  {partition}: "
                f"{len(features):,} windows, "
                f"{positive:,} sensor-fault windows"
            )

            all_windows.append(features)

    if not all_windows:
        raise RuntimeError("No feature windows were generated.")

    print("\nCombining feature windows...")

    result = pd.concat(
        all_windows,
        ignore_index=True,
    )

    # Verify that every numeric feature is finite.
    # Verify that all engineered sensor features are finite.
    # Raw sensor columns are not stored in the window dataset;
    # columns instead look like temperature_mean, rpm_std, etc.

    numeric_feature_columns = [
    column
    for column in result.columns
    if (
        any(
            column.startswith(f"{sensor}_")
            for sensor in SENSOR_FEATURES
        )
        or column == "max_longest_equal_run_any_sensor"
    )
]

    if not numeric_feature_columns:
        raise ValueError(
        "No engineered sensor features were found."
    )

    if not np.isfinite(
        result[numeric_feature_columns].to_numpy()
    ).all():
        raise ValueError(
            "Non-finite feature values found. Inspect preprocessing."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"\nSaving compressed dataset to:\n{OUTPUT_PATH}")

    result.to_csv(
        OUTPUT_PATH,
        index=False,
        compression="gzip",
    )

    print("\n" + "=" * 65)
    print("PREPROCESSING COMPLETE")
    print("=" * 65)

    print(f"Feature rows: {len(result):,}")
    print(f"Total columns: {len(result.columns)}")
    print(f"Engineered numeric features: {len(numeric_feature_columns)}")

    print("\nRows by partition:")
    print(result["partition"].value_counts().to_string())

    print("\nSensor-fault label counts:")
    print(result["sensor_fault"].value_counts().to_string())

    print("\nSensor-fault rate by partition:")
    print(
        result.groupby("partition")["sensor_fault"]
        .agg(["sum", "count", "mean"])
        .to_string()
    )

    print("\nScenario types represented in the windows:")
    print(
        result["scenario_types"]
        .replace("", np.nan)
        .dropna()
        .str.split(";")
        .explode()
        .value_counts()
        .to_string()
    )

    print("\nOutput file created successfully.")


if __name__ == "__main__":
    main()
