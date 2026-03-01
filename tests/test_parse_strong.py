"""Tests for the Strong App parser."""

import os
import sys
import tempfile
import pandas as pd
import pytest

# Add scripts directory to path
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from parse_strong import parse_strong


@pytest.fixture
def sample_strong_xlsx():
    """Create a minimal Strong export Excel file for testing."""
    data = {
        "Fecha": [
            "2026-01-15 08:00:00", "2026-01-15 08:00:00",
            "2026-01-15 08:00:00", "2026-01-15 08:00:00",
            "2026-01-15 08:00:00",
        ],
        "Nombre de entrenamiento": ["Test Workout"] * 5,
        "Duración": ["45m"] * 5,
        "Nombre del ejercicio": [
            "Squat (Barbell)", "Squat (Barbell)", "Squat (Barbell)",
            "Squat (Barbell)", "Pull Up",
        ],
        "Orden de la serie": ["P", "1", "2", "Temporizador de descanso", "1"],
        "Peso": [45.0, 175.0, 175.0, 0.0, 0.0],
        "Rep.": [5, 4, 4, 0, 8],
        "Distancia": [None, None, None, None, None],
        "Segundos": [0, 0, 0, 120, 0],
        "Notas": [None, 7.5, 8.0, None, 7.0],
        "Notas del entrenamiento": [None] * 5,
        "RPE": [None] * 5,
    }
    df = pd.DataFrame(data)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        df.to_excel(f.name, index=False)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def parsed_output(sample_strong_xlsx):
    """Parse the sample file and return the output DataFrame."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        output_path = f.name

    result = parse_strong(sample_strong_xlsx, output_path)
    yield result
    os.unlink(output_path)


class TestParseStrong:
    """Tests for the Strong parser function."""

    def test_filters_rest_timers(self, parsed_output):
        assert "rest" not in parsed_output["set_type"].values, \
            "Rest timers should be filtered out"

    def test_row_count_after_filter(self, parsed_output):
        # 5 rows input, 1 rest timer filtered = 4 rows
        assert len(parsed_output) == 4

    def test_classifies_warmup(self, parsed_output):
        warmup_rows = parsed_output[parsed_output["set_type"] == "warmup"]
        assert len(warmup_rows) == 1, "Should have exactly 1 warmup set"
        assert warmup_rows.iloc[0]["exercise"] == "Squat (Barbell)"

    def test_classifies_working(self, parsed_output):
        working_rows = parsed_output[parsed_output["set_type"] == "working"]
        assert len(working_rows) == 3

    def test_output_columns(self, parsed_output):
        expected = ["date", "workout_name", "exercise", "set_type",
                    "set_num", "weight_lb", "reps", "seconds", "rpe_actual"]
        assert list(parsed_output.columns) == expected

    def test_rpe_numeric(self, parsed_output):
        working = parsed_output[parsed_output["set_type"] == "working"]
        rpe_values = working["rpe_actual"].dropna()
        assert len(rpe_values) > 0, "Should have some RPE values"
        assert rpe_values.dtype == float, "RPE should be float"

    def test_weight_preserved(self, parsed_output):
        squats = parsed_output[
            (parsed_output["exercise"] == "Squat (Barbell)") &
            (parsed_output["set_type"] == "working")
        ]
        assert (squats["weight_lb"] == 175.0).all()

    def test_bodyweight_zero(self, parsed_output):
        pullups = parsed_output[parsed_output["exercise"] == "Pull Up"]
        assert (pullups["weight_lb"] == 0.0).all(), \
            "Bodyweight exercises should have weight_lb = 0"
