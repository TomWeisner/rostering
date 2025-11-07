from __future__ import annotations

from types import SimpleNamespace

import pytest

from rostering.input_data import InputData
from rostering.reporting.reporter import Reporter


class DummyModel:
    def __init__(self, ok=True):
        self._ok = ok

    def precheck(self):
        return (10, 5, self._ok, {}, {})


def make_cfg():
    return SimpleNamespace(DAYS=1, HOURS=1, SKILL_MIN=[[{}]])


def make_result():
    return SimpleNamespace(progress_history=[(0.0, 10.0, 8.0)])


def make_input():
    staff = [SimpleNamespace(skills=set(), holidays=set())]
    allowed = [[True] * 24]
    return InputData(staff=staff, allowed=allowed, is_weekend=[False])


def test_pre_solve_skips_when_no_precheck(capfd):
    reporter = Reporter(make_cfg())
    reporter.pre_solve(object())
    assert "Pre-check" in capfd.readouterr().out


def test_pre_solve_prompts_when_infeasible(monkeypatch):
    reporter = Reporter(make_cfg())
    model = DummyModel(ok=False)
    monkeypatch.setattr(reporter, "_prompt_yes_no_default_yes", lambda msg: False)
    with pytest.raises(SystemExit):
        reporter.pre_solve(model)


def test_post_solve_triggers_render_and_plots(monkeypatch):
    reporter = Reporter(make_cfg(), enable_plots=True)
    calls = []

    def fake_render(cfg, adapter, res, data, num_print_examples=6):
        calls.append("render")

    def fake_hour(*args, **kwargs):
        calls.append("hourly")

    def fake_progress(history):
        calls.append("progress")

    monkeypatch.setattr("rostering.reporting.reporter.render_text_report", fake_render)
    monkeypatch.setattr(
        "rostering.reporting.reporter.show_hour_of_day_histograms", fake_hour
    )
    monkeypatch.setattr(
        "rostering.reporting.reporter.show_solution_progress", fake_progress
    )

    reporter.post_solve(make_result(), make_input())
    assert calls == ["render", "hourly", "progress"]


def test_post_solve_skips_plots_when_disabled(monkeypatch):
    reporter = Reporter(make_cfg(), enable_plots=False)
    called = []
    monkeypatch.setattr(
        "rostering.reporting.reporter.render_text_report",
        lambda *a, **k: called.append("render"),
    )
    reporter.post_solve(SimpleNamespace(progress_history=[(0, 1, 1)]), object())
    assert called == ["render"]
