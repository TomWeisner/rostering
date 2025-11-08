from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

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


def make_cfg():
    return SimpleNamespace(DAYS=1, HOURS=2, SKILL_MIN=[[{"A": 1}, {"A": 1}]])


def make_data():
    staff = [SimpleNamespace(skills={"A"}, holidays=set())]
    allowed = [[True] * 24]
    return InputData(staff=staff, allowed=allowed)


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
