from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from rostering.input_data import InputData

from .adapters import ResultAdapter
from .metrics import compute_coverage_metrics, compute_slot_gaps


def _fmt_float(x: float | None, nd: int = 2, as_pct: bool = False) -> str:
    if x is None:
        return "nan"
    try:
        if pd.isna(x):
            return "nan"
        return f"{float(100 * x):.{nd}f}%" if as_pct else f"{float(x):.{nd}f}"
    except Exception:
        return "nan"


def _print_hours_histogram(df_emp: pd.DataFrame) -> None:
    if df_emp.empty or "hours" not in df_emp.columns:
        print("\nHours distribution: (no data)")
        return
    hours_series = (
        pd.to_numeric(df_emp["hours"], errors="coerce").dropna().round().astype(int)
    )
    counts = hours_series.value_counts().sort_index()
    print("\nHours distribution — how many staff at each total hour:")
    for h, n in counts.items():
        bar = "█" * min(int(n), 50)
        print(f"  {h:>3}h : {n:>4} staff  {bar}")

    top = hours_series.value_counts().sort_values(ascending=False).head(5)
    modes = ", ".join(f"{h}h ({n})" for h, n in zip(top.index, top))
    print(f"\nMost common staff totals: {modes}")


def render_text_report(
    cfg: Any,
    adapter: ResultAdapter,
    res: Any,
    data: InputData,
    *,
    num_print_examples: int = 6,
) -> None:
    status = adapter.status_name(res)
    obj = adapter.objective_value(res)
    avg_run = adapter.avg_consecutive_workday_run(res)
    max_run = adapter.max_consecutive_workday_run(res)

    print(f"Solver status: {status}")
    if status == "INFEASIBLE":
        print(
            "No feasible schedule found. If your solver exposes UNSAT cores/groups, show them here."
        )
        return
    if obj is None:
        print("No trusted solution; exiting.")
        return

    df_emp = adapter.df_emp(res)
    if not df_emp.empty and "hours" in df_emp.columns:
        print(f"\nPer-employee hours (top {num_print_examples}):")
        print(df_emp.head(num_print_examples).to_string(index=False))

        hrs = pd.to_numeric(df_emp["hours"], errors="coerce").to_numpy(dtype=float)
        hrs = hrs[~np.isnan(hrs)]
        if hrs.size:
            mean = float(np.mean(hrs))
            std = float(np.std(hrs, ddof=1)) if hrs.size > 1 else float("nan")
            if hrs.size > 1:
                p5, p95 = np.percentile(hrs, [5.0, 95.0])
            else:
                p5, p95 = float(hrs.min()), float(hrs.max())
            mn, mx = float(np.min(hrs)), float(np.max(hrs))
            print(
                "\nHours distribution across employees: "
                f"mean={_fmt_float(mean)} | std={_fmt_float(std)} | "
                f"p5={_fmt_float(p5)} | p95={_fmt_float(p95)} | "
                f"min={_fmt_float(mn)} | max={_fmt_float(mx)}"
            )

        cap = getattr(cfg, "WEEKLY_MAX_HOURS", None)
        if cap is not None:
            over = df_emp[pd.to_numeric(df_emp["hours"], errors="coerce") > cap]
            if not over.empty:
                print(f"\n⚠️ Employees over cap {cap}h:")
                print(over.to_string(index=False))
            else:
                print(f"\nAll employees within weekly cap ({cap}h).")

    df_shifts = adapter.df_shifts(res)
    if not df_shifts.empty and {"start_hour", "length_h"}.issubset(df_shifts.columns):
        df = df_shifts.copy()
        print("\nShift consistency (means across employees):")
        g = df.groupby("employee_id", sort=False)
        start_std = g["start_hour"].std(ddof=1).mean()
        dur_mean = g["length_h"].mean().mean()
        dur_std = g["length_h"].std(ddof=1).mean()
        print(
            f"duration mean={_fmt_float(float(dur_mean))} | "
            f"duration std≈{_fmt_float(float(dur_std))} | "
            f"start_hour std≈{_fmt_float(float(start_std))}"
        )

    cov = compute_coverage_metrics(cfg, res, data, adapter)
    print(
        f"\nSummary: assigned_people_hours={cov.assigned_people_hours:,} | "
        f"people_hour_lower_bound={cov.people_hour_lower_bound:,} "
        f"(minimum people-hours needed if you only count headcount per hour)"
    )
    print(
        "\nDefinitions:"
        "\n- assigned_people_hours: total person-hours scheduled (people × hours)."
        "\n- people_hour_lower_bound: headcount-only minimum per hour (max single-skill min) summed across grid."
        "\n- skill: one required unit of a skill in an hour (e.g., A:2,B:1 → 3 skill copies)."
        "\n- assignment-hour: one employee assigned to one hour.\n"
    )

    if cov.assigned_people_hours < cov.people_hour_lower_bound:
        print(
            "⚠️ Assigned people-hours are below the lower bound — you cannot meet even headcount minima."
        )

    if cov.skill_demand_hours > 0:
        coverage_ratio = (
            cov.covered_skills / cov.skill_demand_hours
            if cov.skill_demand_hours > 0
            else 0.0
        )
        print(
            f"Skill coverage: covered_skills = {cov.covered_skills:,} / "
            f"skill_demand_hours = {cov.skill_demand_hours:,} "
            f"({_fmt_float(coverage_ratio, nd=1, as_pct=True)})"
        )
        if cov.unmatched_assignments_on_demand > 0:
            print(
                "Unmatched on-demand assignments (people scheduled in demanded hours "
                f"who could not cover any required skill): {cov.unmatched_assignments_on_demand:,}"
            )
        if cov.assignment_hours_in_zero_demand_slots > 0:
            print(
                f"Assignments in zero-demand slots: {cov.assignment_hours_in_zero_demand_slots:,}"
            )
    else:
        print("Skill coverage: (no per-skill minima configured)")

    if avg_run is not None:
        print("\nAvg consecutive days worked = " f"{_fmt_float(float(avg_run))}")
    if max_run is not None:
        print("Max consecutive days worked = " f"{_fmt_float(float(max_run))}")

    print(f"\nObjective value (overall penalty): {obj:,.0f}")

    top_gaps, df_gaps = compute_slot_gaps(cfg, res, data, adapter, top=5)
    problem_rows = df_gaps[(df_gaps["deficit"] > 0) | (df_gaps["unattainable"])]
    if problem_rows.empty:
        print("\nPer-slot gaps: no deficits against per-slot headcount minima.")
    else:
        print("\nTop per-slot gaps (against per-slot headcount minima):")
        print(
            problem_rows.sort_values(
                ["unattainable", "deficit", "required_people_for_slot"],
                ascending=[False, False, False],
            )
            .rename(
                columns={
                    "required_people_for_slot": "required_people",
                    "assigned_people": "assigned",
                    "available_people_upper_bound": "available_upper_bound",
                }
            )
            .head(5)
            .to_string(index=False)
        )

    _print_hours_histogram(df_emp=adapter.df_emp(res))
