from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from rostering.input_data import InputData
from rostering.precheck import precheck_availability

from .adapters import ResultAdapter
from .metrics import compute_coverage_metrics, compute_slot_gaps


class ReportDocument:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []
        self.figures: list[plt.Figure] = []

    def add_text(self, text: str) -> None:
        self.lines.append(text)

    def add_figure(self, fig: plt.Figure) -> None:
        self.figures.append(fig)

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with PdfPages(self.path) as pdf:
            if self.lines:
                fig, ax = plt.subplots(figsize=(8.27, 11.69))
                ax.axis("off")
                text = "\n".join(self.lines)
                ax.text(
                    0.01,
                    0.99,
                    text,
                    ha="left",
                    va="top",
                    fontsize=8,
                    family="monospace",
                )
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
            elif not self.figures:
                fig, ax = plt.subplots(figsize=(8.27, 11.69))
                ax.axis("off")
                ax.text(
                    0.5,
                    0.5,
                    "Report contains no data.",
                    ha="center",
                    va="center",
                    fontsize=12,
                )
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
            for fig in self.figures:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)


_ACTIVE_REPORT: Optional[ReportDocument] = None


def set_active_report(doc: Optional[ReportDocument]) -> None:
    global _ACTIVE_REPORT
    _ACTIVE_REPORT = doc


def get_active_report() -> Optional[ReportDocument]:
    return _ACTIVE_REPORT


def _log_print(*args, **kwargs) -> None:
    from io import StringIO

    buf = StringIO()
    kwargs_copy = kwargs.copy()
    kwargs_copy["file"] = buf
    print(*args, **kwargs_copy)
    print(*args, **kwargs)
    if _ACTIVE_REPORT is not None:
        _ACTIVE_REPORT.add_text(buf.getvalue().rstrip("\n"))


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
        _log_print("\nHours distribution: (no data)")
        return
    hours_series = (
        pd.to_numeric(df_emp["hours"], errors="coerce").dropna().round().astype(int)
    )
    counts = hours_series.value_counts().sort_index()
    _log_print("\nHours distribution — how many staff at each total hour:")
    for h, n in counts.items():
        bar = "█" * min(int(n), 50)
        _log_print(f"  {h:>3}h : {n:>4} staff  {bar}")

    top = hours_series.value_counts().sort_values(ascending=False).head(5)
    modes = ", ".join(f"{h}h ({n})" for h, n in zip(top.index, top))
    _log_print(f"\nMost common staff totals: {modes}")


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

    _log_print(f"Solver status: {status}")
    if status == "INFEASIBLE":
        _print_unsat_core(cfg, data, res)
        return
    if status == "UNKNOWN":
        _log_print("Solver ran out of time before proving feasibility/optimality.")
    if obj is None:
        _log_print("No trusted solution; exiting.")
        return

    df_emp = adapter.df_emp(res)
    if not df_emp.empty and "hours" in df_emp.columns:
        _log_print(f"\nPer-employee hours (top {num_print_examples}):")
        _log_print(df_emp.head(num_print_examples).to_string(index=False))

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
            _log_print(
                "\nHours distribution across employees: "
                f"mean={_fmt_float(mean)} | std={_fmt_float(std)} | "
                f"p5={_fmt_float(p5)} | p95={_fmt_float(p95)} | "
                f"min={_fmt_float(mn)} | max={_fmt_float(mx)}"
            )

        cap = getattr(cfg, "WEEKLY_MAX_HOURS", None)
        if cap is not None:
            over = df_emp[pd.to_numeric(df_emp["hours"], errors="coerce") > cap]
            if not over.empty:
                _log_print(f"\n⚠️ Employees over cap {cap}h:")
                _log_print(over.to_string(index=False))
            else:
                _log_print(f"\nAll employees within weekly cap ({cap}h).")

    df_shifts = adapter.df_shifts(res)
    if not df_shifts.empty and {"start_hour", "length_h"}.issubset(df_shifts.columns):
        df = df_shifts.copy()
        _log_print("\nShift consistency (means across employees):")
        g = df.groupby("employee_id", sort=False)
        start_std = g["start_hour"].std(ddof=1).mean()
        dur_mean = g["length_h"].mean().mean()
        dur_std = g["length_h"].std(ddof=1).mean()
        _log_print(
            f"duration mean={_fmt_float(float(dur_mean))} | "
            f"duration std≈{_fmt_float(float(dur_std))} | "
            f"start_hour std≈{_fmt_float(float(start_std))}"
        )

    cov = compute_coverage_metrics(cfg, res, data, adapter)
    _log_print(
        f"\nSummary: assigned_people_hours={cov.assigned_people_hours:,} | "
        f"people_hour_lower_bound={cov.people_hour_lower_bound:,} "
        f"(minimum people-hours needed if you only count headcount per hour)"
    )
    _log_print(
        "\nDefinitions:"
        "\n- assigned_people_hours: total person-hours scheduled (people × hours)."
        "\n- people_hour_lower_bound: headcount-only minimum per hour (max single-skill min) summed across grid."
        "\n- skill: one required unit of a skill in an hour (e.g., A:2,B:1 → 3 skill copies)."
        "\n- assignment-hour: one employee assigned to one hour.\n"
    )

    if cov.assigned_people_hours < cov.people_hour_lower_bound:
        _log_print(
            "⚠️ Assigned people-hours are below the lower bound — you cannot meet even headcount minima."
        )

    if cov.skill_demand_hours > 0:
        coverage_ratio = (
            cov.covered_skills / cov.skill_demand_hours
            if cov.skill_demand_hours > 0
            else 0.0
        )
        _log_print(
            f"Skill coverage: covered_skills = {cov.covered_skills:,} / "
            f"skill_demand_hours = {cov.skill_demand_hours:,} "
            f"({_fmt_float(coverage_ratio, nd=1, as_pct=True)})"
        )
        if cov.unmatched_assignments_on_demand > 0:
            _log_print(
                "Unmatched on-demand assignments (people scheduled in demanded hours "
                f"who could not cover any required skill): {cov.unmatched_assignments_on_demand:,}"
            )
        if cov.assignment_hours_in_zero_demand_slots > 0:
            _log_print(
                f"Assignments in zero-demand slots: {cov.assignment_hours_in_zero_demand_slots:,}"
            )
    else:
        _log_print("Skill coverage: (no per-skill minima configured)")

    if avg_run is not None:
        _log_print("\nAvg consecutive days worked = " f"{_fmt_float(float(avg_run))}")
    if max_run is not None:
        _log_print("Max consecutive days worked = " f"{_fmt_float(float(max_run))}")

    _log_print(f"\nObjective value (overall penalty): {obj:,.0f}")

    top_gaps, df_gaps = compute_slot_gaps(cfg, res, data, adapter, top=5)
    problem_rows = df_gaps[(df_gaps["deficit"] > 0) | (df_gaps["unattainable"])]
    if problem_rows.empty:
        _log_print("\nPer-slot gaps: no deficits against per-slot headcount minima.")
    else:
        _log_print("\nTop per-slot gaps (against per-slot headcount minima):")
        _log_print(
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


def _print_unsat_core(
    cfg: Any, data: InputData, res: Any, *, max_per_group: int = 10
) -> None:
    groups = getattr(res, "unsat_core_groups", {}) or {}
    if not groups:
        _log_print("No feasible schedule found.")
        if not getattr(cfg, "ENABLE_UNSAT_CORE", True):
            _log_print(
                "ENABLE_UNSAT_CORE is disabled on this Config, so the solver cannot expose UNSAT cores."
            )
        _print_precheck_summary(cfg, data)
        return

    _log_print("No feasible schedule found. UNSAT constraints grouped by rule tag:")
    for rule, labels in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        total = len(labels)
        preview = labels[:max_per_group]
        _log_print(f"- {rule}: {total} constraint(s) in core")
        for lab in preview:
            _log_print(f"    • {lab}")
        if total > max_per_group:
            _log_print(f"    • … {total - max_per_group} more")


def _print_precheck_summary(cfg: Any, data: InputData) -> None:
    try:
        cap, dem, ok_cap, buckets, stats = precheck_availability(
            cfg, data, verbose=False
        )
    except Exception:
        _log_print(
            "Capacity diagnostic unavailable (precheck raised an error while recomputing statistics)."
        )
        return

    _log_print(
        f"Capacity upper bound = {cap:,} people-hours | "
        f"lower bound demand = {dem:,} | "
        f"cap {'≥' if ok_cap else '<'} demand"
    )

    deficits = [
        (skill, info)
        for skill, info in stats.items()
        if info.get("min_slack", 0) < 0 or info.get("shortfall_slots", 0) > 0
    ]
    if not deficits:
        _log_print("No per-skill shortfalls detected in the pre-check.")
        return

    deficits.sort(
        key=lambda item: (item[1].get("min_slack", 0), -item[1].get("required", 0))
    )
    _log_print("Most constrained skills (based on pre-check):")
    for skill, info in deficits[:5]:
        _log_print(
            f"  - {skill}: required={info['required']:,}, available={info['available']:,}, "
            f"min_slack={info['min_slack']}, shortfall_slots={info['shortfall_slots']}"
        )
        examples = buckets.get(skill, [])[:5]
        if examples:
            example_str = ", ".join(
                f"d={d},h={h:02d} (avail={avail})" for d, h, avail in examples
            )
            _log_print(f"      e.g. {example_str}")
