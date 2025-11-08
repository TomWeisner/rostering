from __future__ import annotations

from datetime import datetime

import matplotlib
import pandas as pd

matplotlib.use("Agg", force=True)
from rostering.config import Config
from rostering.generate.staff import Staff
from rostering.input_data import InputData
from rostering.reporting.adapters import ResultAdapter
from rostering.reporting.plots import (
    show_hour_of_day_histograms,
    show_solution_progress,
)


class TinyAdapter(ResultAdapter):
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def status_name(self, res):  # pragma: no cover - unused
        return "FEASIBLE"

    def objective_value(self, res):  # pragma: no cover - unused
        return None

    def avg_consecutive_workday_run(self, res):  # pragma: no cover - unused
        return None

    def max_consecutive_workday_run(self, res):  # pragma: no cover - unused
        return None

    def df_emp(self, res):  # pragma: no cover - unused
        return pd.DataFrame()

    def df_sched(self, res):
        return self._df

    def df_shifts(self, res):
        return pd.DataFrame()


def make_cfg() -> Config:
    cfg = Config(
        N=1,
        DAYS=1,
        HOURS=24,
        START_DATE=datetime(2024, 1, 1),
        MIN_SHIFT_HOURS=1,
        MAX_SHIFT_HOURS=1,
        REST_HOURS=0,
        TIME_LIMIT_SEC=1.0,
        NUM_PARALLEL_WORKERS=1,
        LOG_SOLUTIONS_FREQUENCY_SECONDS=1.0,
    )
    cfg.SKILL_MIN = [[{"A": 1} for _ in range(cfg.HOURS)]]
    return cfg


def make_data():
    staff = [
        Staff(
            id=0,
            name="A",
            band=1,
            skills=["A"],
            is_night_worker=False,
            max_consec_days=None,
        )
    ]
    cfg = make_cfg()
    allowed = [[True] * cfg.HOURS]
    return InputData(staff=staff, cfg=cfg, allowed=allowed)


def test_hour_of_day_histogram_saves(monkeypatch):
    saved = {}

    def fake_save(fig, name):
        saved["name"] = name

    monkeypatch.setattr("rostering.reporting.plots._save_and_show", fake_save)
    df = pd.DataFrame({"employee_id": [0], "day": [0], "hour": [0]})
    adapter = TinyAdapter(df)

    show_hour_of_day_histograms(make_cfg(), object(), make_data(), adapter)
    assert saved["name"] == "hour_of_day_skill_bar_chart.png"


def test_solution_progress_plot_saves(monkeypatch):
    saved = {}

    def fake_save(fig, name):
        saved["name"] = name

    monkeypatch.setattr("rostering.reporting.plots._save_and_show", fake_save)
    history = [(0.0, 100.0, 90.0), (1.0, 80.0, 70.0)]

    show_solution_progress(history)
    assert saved["name"] == "solution_progress.png"
