import os
import pytest
import pandas as pd

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


@pytest.fixture
def data_dir():
    return DATA_DIR


@pytest.fixture
def workouts():
    return pd.read_csv(os.path.join(DATA_DIR, "workouts.csv"), parse_dates=["start_date", "end_date"])


@pytest.fixture
def daily_health():
    return pd.read_csv(os.path.join(DATA_DIR, "daily_health.csv"), parse_dates=["date"])


@pytest.fixture
def body_composition():
    return pd.read_csv(os.path.join(DATA_DIR, "body_composition.csv"), parse_dates=["date"])


@pytest.fixture
def vo2max():
    return pd.read_csv(os.path.join(DATA_DIR, "vo2max.csv"), parse_dates=["date"])


@pytest.fixture
def strong_log():
    return pd.read_csv(os.path.join(DATA_DIR, "strong_log.csv"))
