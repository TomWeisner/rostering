# rostering/result_types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class SolveResult:
    """Structured output of a solve run."""

    status_name: str
    objective_value: Optional[float]
    df_sched: pd.DataFrame
    df_shifts: pd.DataFrame
    df_emp: pd.DataFrame
    avg_run: float
    unsat_core_groups: dict[str, list[str]]
