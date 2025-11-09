from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from rostering.config import Config
from rostering.input_data import InputData
from rostering.reporting.adapters import PandasResultAdapter
from rostering.reporting.text_report import render_text_report
from rostering.staff import Staff


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
        WEEKLY_MAX_HOURS=10,
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
    return InputData(staff=staff, cfg=cfg)


def make_result(status: str = "FEASIBLE"):
    return SimpleNamespace(
        status_name=status,
        objective_value=123.0,
        avg_run=2.0,
        max_run=3.0,
        df_emp=pd.DataFrame({"employee_id": [0], "hours": [8]}),
        df_sched=pd.DataFrame({"employee_id": [0], "day": [0], "hour": [0]}),
        df_shifts=pd.DataFrame(
            {
                "employee_id": [0],
                "start_day": [0],
                "start_hour": [0],
                "length_h": [8],
            }
        ),
    )


def test_render_text_report_prints_summary(capsys):
    cfg = make_cfg()
    data = make_data()
    res = make_result()
    adapter = PandasResultAdapter()

    render_text_report(cfg, adapter, res, data, num_print_examples=1)
    out = capsys.readouterr().out
    assert "Solver status: FEASIBLE" in out
    assert "assigned_people_hours" in out
    assert "Objective value" in out


def test_render_text_report_handles_infeasible(capsys):
    cfg = make_cfg()
    data = make_data()
    res = make_result(status="INFEASIBLE")
    adapter = PandasResultAdapter()

    render_text_report(cfg, adapter, res, data)
    out = capsys.readouterr().out
    assert "INFEASIBLE" in out
    assert "No feasible schedule" in out
