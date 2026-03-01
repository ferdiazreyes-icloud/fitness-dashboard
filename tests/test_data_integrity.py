"""Tests for data integrity of CSVs used by the dashboard."""

import os
import pandas as pd
import pytest

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

EXPECTED_CSVS = [
    "workouts.csv",
    "daily_health.csv",
    "body_composition.csv",
    "activity_summary.csv",
    "weekly_summary.csv",
    "vo2max.csv",
    "strong_log.csv",
    "training_plan.csv",
]


class TestCSVsExist:
    """All required CSVs must exist and be non-empty."""

    @pytest.mark.parametrize("filename", EXPECTED_CSVS)
    def test_csv_exists(self, filename):
        filepath = os.path.join(DATA_DIR, filename)
        assert os.path.exists(filepath), f"{filename} not found in data/"

    @pytest.mark.parametrize("filename", EXPECTED_CSVS)
    def test_csv_not_empty(self, filename):
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            df = pd.read_csv(filepath, on_bad_lines="skip")
            assert len(df) > 0, f"{filename} is empty"


class TestWorkoutsSchema:
    """Workouts CSV must have expected columns and valid data."""

    REQUIRED_COLUMNS = [
        "id", "activity_type", "start_date", "end_date",
        "duration_min", "distance_km", "energy_kcal",
        "hr_avg", "hr_max",
    ]

    def test_has_required_columns(self, workouts):
        for col in self.REQUIRED_COLUMNS:
            assert col in workouts.columns, f"Missing column: {col}"

    def test_dates_are_valid(self, workouts):
        assert workouts["start_date"].notna().all(), "Some start_date values are NaT"
        assert (workouts["start_date"].dt.year >= 2017).all(), "Found dates before 2017"
        assert (workouts["start_date"].dt.year <= 2027).all(), "Found dates after 2027"

    def test_duration_non_negative(self, workouts):
        valid = workouts[workouts["duration_min"].notna()]
        assert (valid["duration_min"] >= 0).all(), "Found negative durations"


class TestDailyHealthSchema:
    """Daily health CSV must have expected columns."""

    REQUIRED_COLUMNS = ["date", "resting_hr", "hrv_sdnn_ms", "steps", "sleep_duration_hr"]

    def test_has_required_columns(self, daily_health):
        for col in self.REQUIRED_COLUMNS:
            assert col in daily_health.columns, f"Missing column: {col}"

    def test_dates_are_valid(self, daily_health):
        assert daily_health["date"].notna().all(), "Some date values are NaT"


class TestBodyComposition:
    """Body composition data must be within physiological ranges."""

    def test_weight_range(self, body_composition):
        valid = body_composition[body_composition["weight_kg"].notna()]
        assert (valid["weight_kg"] >= 40).all(), "Found weight < 40 kg"
        assert (valid["weight_kg"] <= 200).all(), "Found weight > 200 kg"

    def test_body_fat_range(self, body_composition):
        valid = body_composition[body_composition["body_fat_pct"].notna()]
        assert (valid["body_fat_pct"] >= 3).all(), "Found body fat < 3%"
        assert (valid["body_fat_pct"] <= 60).all(), "Found body fat > 60%"


class TestVO2Max:
    """VO2Max values must be within physiological range."""

    def test_vo2max_range(self, vo2max):
        valid = vo2max[vo2max["vo2max"].notna()]
        assert (valid["vo2max"] >= 20).all(), "Found VO2Max < 20"
        assert (valid["vo2max"] <= 80).all(), "Found VO2Max > 80"


class TestStrongLog:
    """Strong log must have correct schema and valid RPE values."""

    REQUIRED_COLUMNS = [
        "date", "workout_name", "exercise", "set_type",
        "set_num", "weight_lb", "reps", "seconds", "rpe_actual",
    ]

    def test_has_required_columns(self, strong_log):
        for col in self.REQUIRED_COLUMNS:
            assert col in strong_log.columns, f"Missing column: {col}"

    def test_set_types_valid(self, strong_log):
        valid_types = {"working", "warmup"}
        assert set(strong_log["set_type"].unique()).issubset(valid_types), \
            f"Unexpected set types: {set(strong_log['set_type'].unique()) - valid_types}"

    def test_rpe_range(self, strong_log):
        valid = strong_log[strong_log["rpe_actual"].notna()]
        if len(valid) > 0:
            assert (valid["rpe_actual"] >= 1).all(), "Found RPE < 1"
            assert (valid["rpe_actual"] <= 10).all(), "Found RPE > 10"

    def test_weight_non_negative(self, strong_log):
        assert (strong_log["weight_lb"] >= 0).all(), "Found negative weight"
