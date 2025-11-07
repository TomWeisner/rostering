from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from rostering.reporting.adapters import PandasResultAdapter


def test_df_sched_normalises_columns():
    adapter = PandasResultAdapter()
    df = pd.DataFrame(
        {
            "Employee_ID": [3, 4],
            "Day": [0, 0],
            "Hour": [1, 2],
            "extra": [1, 2],
        }
    )
    res = SimpleNamespace(df_sched=df)

    normalized = adapter.df_sched(res)

    assert list(normalized.columns) == ["employee_id", "day", "hour"]
    assert normalized.iloc[0].tolist() == [3, 0, 1]


def test_df_shifts_handles_dates_and_missing_cols():
    adapter = PandasResultAdapter()
    df = pd.DataFrame(
        {
            "employee_id": [1],
            "start_date": ["2024-01-01"],
            "start_hour": [6],
            "length_h": [8],
        }
    )
    res = SimpleNamespace(df_shifts=df)

    normalized = adapter.df_shifts(res)

    assert list(normalized.columns) == [
        "employee_id",
        "start_day",
        "start_hour",
        "length_h",
    ]
    assert normalized.iloc[0].tolist() == [1, 0, 6, 8]
