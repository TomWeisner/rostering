# rostering/extract.py
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

from rostering.build import BuildContext


def _has_skill(staff_obj, name: str) -> bool:
    """
    Robustly check whether a Staff has a given skill.
    Supports Staff.skills as set[str] or dict[str, bool], with a fallback
    to legacy boolean attributes (e.g., skillA) if present.
    """
    if hasattr(staff_obj, "skills"):
        sk = getattr(staff_obj, "skills")
        # dict[str, bool]
        if isinstance(sk, dict):
            return bool(sk.get(name, False))
        # set / list / other iterables
        try:
            return name in sk
        except TypeError:
            pass
    # legacy fallback (e.g., skillA / skillB)
    return bool(getattr(staff_obj, f"skill{name}", getattr(staff_obj, name, False)))


def extract_hourly(ctx: BuildContext, solver: cp_model.CpSolver) -> pd.DataFrame:
    """Return the hour-level schedule dataframe."""
    C = ctx.cfg
    rows: list[dict] = []
    for d in range(C.DAYS):
        for h in range(C.HOURS):
            for e in range(C.N):
                if solver.Value(ctx.x[(e, d, h)]) == 1:
                    s = ctx.data.staff[e]
                    rows.append(
                        {
                            "date": (C.START_DATE + timedelta(days=d))
                            .date()
                            .isoformat(),
                            "day_index": d,
                            "hour": h,
                            "employee_id": e,
                            "name": s.name,
                            "band": s.band,
                            # derive booleans from unified skills
                            "skillA": _has_skill(s, "A"),
                            "skillB": _has_skill(s, "B"),
                        }
                    )
    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "day_index",
                "hour",
                "employee_id",
                "name",
                "band",
                "skillA",
                "skillB",
            ]
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["date", "hour", "employee_id"])
        .reset_index(drop=True)
    )


def extract_shifts(ctx: BuildContext, solver: cp_model.CpSolver) -> pd.DataFrame:
    """Return the interval-level (one per person/day) dataframe with realized hours."""
    C = ctx.cfg
    shift_rows: list[dict] = []
    for e in range(C.N):
        for d in range(C.DAYS):
            if solver.Value(ctx.y[(e, d)]) == 1:
                sH = int(solver.Value(ctx.S[(e, d)]))
                Lh = int(solver.Value(ctx.L[(e, d)]))
                end_total = sH + Lh
                start_dt = C.START_DATE + timedelta(days=d)
                if end_total <= 24:
                    end_dt = start_dt
                    end_h = end_total
                else:
                    end_dt = start_dt + timedelta(days=1)
                    end_h = end_total - 24
                shift_rows.append(
                    {
                        "employee_id": e,
                        "name": ctx.data.staff[e].name,
                        "start_date": start_dt.date().isoformat(),
                        "start_hour": sH,
                        "end_date": end_dt.date().isoformat(),
                        "end_hour": end_h,
                        "model_length_h": Lh,
                        "day_index": d,
                    }
                )
    if not shift_rows:
        return pd.DataFrame(
            columns=[
                "employee_id",
                "name",
                "start_date",
                "start_hour",
                "end_date",
                "end_hour",
                "model_length_h",
                "day_index",
            ]
        )
    df = (
        pd.DataFrame(shift_rows)
        .sort_values(["start_date", "start_hour", "employee_id"])
        .reset_index(drop=True)
    )
    return df


def extract_employee_totals(
    ctx: BuildContext, solver: cp_model.CpSolver
) -> pd.DataFrame:
    """Return per-employee totals dataframe."""
    C = ctx.cfg
    rows: list[dict] = []
    for e in range(C.N):
        hours = sum(
            solver.Value(ctx.x[(e, d, h)])
            for d in range(C.DAYS)
            for h in range(C.HOURS)
        )
        s = ctx.data.staff[e]
        rows.append(
            {
                "id": e,
                "name": s.name,
                "band": s.band,
                # derive skill flags from unified skills
                "A": int(_has_skill(s, "A")),
                "B": int(_has_skill(s, "B")),
                "night": int(getattr(s, "is_night_worker", 0)),
                "hours": int(hours),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["id", "name", "band", "A", "B", "night", "hours"])
    return pd.DataFrame(rows).sort_values(["hours", "id"], ascending=[False, True])


def compute_avg_run(ctx: BuildContext, solver: cp_model.CpSolver) -> float:
    """Compute average run length over positive run values."""
    if not ctx.runlen:
        return 0.0
    vals = [
        int(solver.Value(ctx.runlen[(e, d)]))
        for e in range(ctx.cfg.N)
        for d in range(ctx.cfg.DAYS)
    ]
    pos = [v for v in vals if v > 0]
    return float(np.mean(pos)) if pos else 0.0
