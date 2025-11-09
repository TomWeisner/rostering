from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from rostering.config import Config
from rostering.input_data import InputData
from rostering.reporting.reporter import Reporter
from rostering.staff import Staff


class DummyModel:
    def __init__(self, ok=True):
        self._ok = ok

    def precheck(self):
        return (10, 5, self._ok, {}, {})


def make_cfg():
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
    cfg.SKILL_MIN = [[{} for _ in range(cfg.HOURS)]]
    return cfg


def make_result():
    return SimpleNamespace(status_name="FEASIBLE", progress_history=[(0.0, 10.0, 8.0)])


def make_input():
    staff = [
        Staff(
            id=0,
            name="Test",
            band=1,
            skills=["ANY"],
            is_night_worker=False,
            max_consec_days=None,
        )
    ]
    cfg = make_cfg()
    return InputData(staff=staff, cfg=cfg)


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
    monkeypatch.setattr(
        "rostering.reporting.reporter.ReportDocument.write", lambda self: None
    )

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
        "rostering.reporting.reporter.ReportDocument.write", lambda self: None
    )
    monkeypatch.setattr(
        "rostering.reporting.reporter.render_text_report",
        lambda *a, **k: called.append("render"),
    )
    reporter.post_solve(make_result(), make_input())
    assert called == ["render"]


def test_post_solve_skips_everything_when_infeasible(monkeypatch):
    reporter = Reporter(make_cfg(), enable_plots=True)
    called = []
    monkeypatch.setattr(
        "rostering.reporting.reporter.ReportDocument.write", lambda self: None
    )
    monkeypatch.setattr(
        "rostering.reporting.reporter.render_text_report",
        lambda *a, **k: called.append("render"),
    )
    monkeypatch.setattr(
        "rostering.reporting.reporter.show_hour_of_day_histograms",
        lambda *a, **k: called.append("hourly"),
    )
    monkeypatch.setattr(
        "rostering.reporting.reporter.show_solution_progress",
        lambda *a, **k: called.append("progress"),
    )

    reporter.post_solve(SimpleNamespace(status_name="INFEASIBLE"), make_input())
    assert called == []
