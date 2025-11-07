from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from rostering.input_data import InputData
from rostering.reporting.adapters import PandasResultAdapter
from rostering.reporting.text_report import render_text_report


def make_cfg():
    return SimpleNamespace(
        DAYS=1,
        HOURS=1,
        WEEKLY_MAX_HOURS=10,
        SKILL_MIN=[[{"A": 1}]],
    )


def make_data():
    staff = [SimpleNamespace(skills={"A"}, holidays=set())]
    allowed = [[True] * 24]
    return InputData(staff=staff, allowed=allowed, is_weekend=[False])


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
