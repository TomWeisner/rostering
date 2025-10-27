from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol, Sequence, cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rostering.data import InputData
from rostering.precheck import print_precheck_header, print_skill_status
from rostering.result_types import SolveResult

# ----------------------------- Adapter Layer -----------------------------


class ResultAdapter(Protocol):
    """
    Minimal interface the Reporter needs to work with *any* model/solution object.

    Implement one adapter per model family if your result objects differ.
    """

    def status_name(self, res: Any) -> str: ...
    def objective_value(self, res: Any) -> Optional[float]: ...
    def avg_consecutive_workday_run(self, res: Any) -> Optional[float]: ...
    def max_consecutive_workday_run(self, res: Any) -> Optional[int]: ...

    def df_emp(self, res: Any) -> pd.DataFrame:
        """Return a DataFrame with at least: ['employee_id', 'hours'] (hours can be float)."""
        ...

    def df_sched(self, res: Any) -> pd.DataFrame:
        """
        Return a per-hour schedule DataFrame with columns:
        ['employee_id', 'day', 'hour'] (all ints).
        If unavailable, return an empty DataFrame.
        """
        ...

    def df_shifts(self, res: Any) -> pd.DataFrame:
        """
        Return a per-shift DataFrame with columns:
        ['employee_id', 'start_day', 'start_hour', 'length_h']
        If unavailable, return an empty DataFrame.
        """
        ...


# Default adapter for your current SolveResult layout
class PandasResultAdapter:
    def status_name(self, res: Any) -> str:
        return getattr(res, "status_name", "UNKNOWN")

    def objective_value(self, res: Any) -> Optional[float]:
        return cast(Optional[float], getattr(res, "objective_value", None))

    def avg_consecutive_workday_run(self, res: Any) -> Optional[float]:
        return cast(Optional[float], getattr(res, "avg_run", None))

    def max_consecutive_workday_run(self, res: Any) -> Optional[int]:
        return cast(Optional[int], getattr(res, "max_run", None))

    def df_emp(self, res: Any) -> pd.DataFrame:
        df = cast(pd.DataFrame, getattr(res, "df_emp", pd.DataFrame()))
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    def df_sched(self, res: Any) -> pd.DataFrame:
        df = cast(pd.DataFrame, getattr(res, "df_sched", pd.DataFrame()))
        if df.empty:
            return df
        cols = {str(c).lower(): c for c in df.columns}
        req = ("employee_id", "day", "hour")
        if all(k in cols for k in req):
            out = df[[cols["employee_id"], cols["day"], cols["hour"]]].copy()
            out.columns = ["employee_id", "day", "hour"]
            return out.astype({"employee_id": int, "day": int, "hour": int})
        return pd.DataFrame()

    def df_shifts(self, res: Any) -> pd.DataFrame:
        df = cast(pd.DataFrame, getattr(res, "df_shifts", pd.DataFrame()))
        if df.empty:
            return df

        sc = {str(c).lower(): c for c in df.columns}

        emp_col = next(
            (
                sc[c]
                for c in ("employee_id", "emp_id", "e", "worker_id", "staff_id")
                if c in sc
            ),
            None,
        )
        start_day_col = next(
            (sc[c] for c in ("start_day", "day", "day_index", "day_idx") if c in sc),
            None,
        )
        start_hour_col = next(
            (sc[c] for c in ("start_hour", "hour", "h") if c in sc), None
        )
        length_col = next(
            (
                sc[c]
                for c in (
                    "length_h",
                    "model_length_h",
                    "dur_h",
                    "duration_h",
                    "duration",
                )
                if c in sc
            ),
            None,
        )

        # If day is given via a date, convert to day index.
        if not start_day_col:
            date_col = next(
                (sc[c] for c in ("start_date", "date", "day_date") if c in sc), None
            )
            if date_col:
                base = pd.to_datetime(df[date_col]).min()
                df = df.assign(start_day=(pd.to_datetime(df[date_col]) - base).dt.days)
                start_day_col = "start_day"

        if not all([emp_col, start_day_col, start_hour_col, length_col]):
            return pd.DataFrame()

        out = df[[emp_col, start_day_col, start_hour_col, length_col]].copy()
        out.columns = ["employee_id", "start_day", "start_hour", "length_h"]
        out["employee_id"] = pd.to_numeric(out["employee_id"], errors="coerce").astype(
            "Int64"
        )
        out["start_day"] = pd.to_numeric(out["start_day"], errors="coerce").astype(
            "Int64"
        )
        out["start_hour"] = pd.to_numeric(out["start_hour"], errors="coerce").astype(
            "Int64"
        )
        out["length_h"] = pd.to_numeric(out["length_h"], errors="coerce").astype(
            "Int64"
        )
        out = out.dropna().astype(int)
        return out


# ----------------------------- Domain Types -----------------------------


@dataclass(frozen=True)
class SlotRequirement:
    """Per (day, hour) requirement summarised as max per-slot people and per-skill minima."""

    required_people_for_slot: int  # max_s SKILL_MIN[d][h][s]
    per_skill_minima: dict[str, int]


@dataclass(frozen=True)
class CoverageMetrics:
    """
    Clear naming for the key quantities:

    - skill_demand_hours: total number of skills demanded across all (d,h)
    - people_hour_lower_bound: sum over (d,h) of max_s SKILL_MIN[d][h][s]
    - assigned_people_hours: total number of employee-hours actually assigned (counting people per hour)
    - assignment_hours_on_demanded_slots: hours assigned in slots where demand > 0
    - assignment_hours_in_zero_demand_slots: hours assigned in slots where demand == 0
    - covered_skill_copies: greedy upper-bound match of assigned employees to demanded skill copies
    - unmatched_assignments_on_demand: assigned employees that did not match any demanded skill at that hour
    """

    skill_demand_hours: int
    people_hour_lower_bound: int
    assigned_people_hours: int
    assignment_hours_on_demanded_slots: int
    assignment_hours_in_zero_demand_slots: int
    covered_skill_copies: int
    unmatched_assignments_on_demand: int


@dataclass(frozen=True)
class SlotGap:
    """Gap record for a single (day, hour)."""

    day: int
    hour: int
    required_people_for_slot: int
    assigned_people: int
    available_people_upper_bound: int
    deficit: int  # max(required - assigned, 0)
    unattainable: bool  # required_people_for_slot > available_people_upper_bound


# ----------------------------- Reporter Core -----------------------------


class Reporter:
    """
    High-level orchestrator:
      - computes metrics from inputs,
      - renders a human-readable report.
    """

    def __init__(
        self,
        cfg: Any,
        adapter: ResultAdapter | None = None,
        num_print_examples: int = 6,
    ) -> None:
        """
        cfg must expose:
          - DAYS: int
          - HOURS: int
          - SKILL_MIN: list[list[dict[str, int]]] with shape [DAYS][HOURS]
          - WEEKLY_MAX_HOURS (Optional[int])
          - allowed mask on data, and staff holidays are read from InputData in gap calc.
        """
        self.cfg = cfg
        self.adapter = adapter or PandasResultAdapter()
        self.num_print_examples = num_print_examples

    # --------- utilities ---------

    @staticmethod
    def _fmt_float(x: Optional[float], nd: int = 2, as_pct: bool = False) -> str:
        if x is None:
            return "nan"
        try:
            if pd.isna(x):
                return "nan"
            return f"{float(100*x):.{nd}f}%" if as_pct else f"{float(x):.{nd}f}"
        except Exception:
            return "nan"

    # --------- core transforms ---------

    def _slot_requirements(self) -> list[list[SlotRequirement]]:
        """Build a grid of SlotRequirement from cfg.SKILL_MIN."""
        D, H = int(self.cfg.DAYS), int(self.cfg.HOURS)
        skill_min = getattr(self.cfg, "SKILL_MIN", None) or {}
        out: list[list[SlotRequirement]] = []
        for d in range(D):
            row: list[SlotRequirement] = []
            for h in range(H):
                slot = skill_min[d][h] or {}
                req = max(slot.values()) if slot else 0
                row.append(
                    SlotRequirement(
                        required_people_for_slot=int(req),
                        per_skill_minima={k: int(v) for k, v in slot.items()},
                    )
                )
            out.append(row)
        return out

    def _assigned_sets(self, res: Any) -> dict[tuple[int, int], set[int]]:
        """
        Build {(day, hour) -> set(employee_id)} using adapter:
        - Prefer per-hour df_sched
        - Fallback to expanding df_shifts
        """
        D, H = int(self.cfg.DAYS), int(self.cfg.HOURS)
        per_slot: dict[tuple[int, int], set[int]] = {}

        # Try df_sched
        sched = self.adapter.df_sched(res)
        if not sched.empty:
            for _, r in sched.iterrows():
                d, h, e = int(r["day"]), int(r["hour"]), int(r["employee_id"])
                if 0 <= d < D and 0 <= h < H:
                    per_slot.setdefault((d, h), set()).add(e)
            return per_slot

        # Fallback df_shifts
        shifts = self.adapter.df_shifts(res)
        if shifts.empty:
            return per_slot

        for _, r in shifts.iterrows():
            e = int(r["employee_id"])
            d0 = int(r["start_day"])
            h0 = int(r["start_hour"])
            Lh = int(r["length_h"])
            for t in range(Lh):
                d = d0 + (h0 + t) // H
                h = (h0 + t) % H
                if 0 <= d < D and 0 <= h < H:
                    per_slot.setdefault((d, h), set()).add(e)
        return per_slot

    @staticmethod
    def _greedy_cover(
        assigned_emp_ids: Iterable[int],
        slot_require: dict[str, int],
        staff_skills: Sequence[dict[str, bool] | set[str]],
    ) -> tuple[int, int]:
        """
        Return (covered_skill_copies, unmatched_assignments_on_demand) for a single slot.

        Each employee can cover at most one skill-copy in that hour.
        We greedily allocate rarer skills first.

        staff_skills[e] must be either set(str) or dict(str->bool).
        """
        assigned = list(assigned_emp_ids)
        if not assigned or not slot_require:
            return (0, 0)

        # Flatten demand into a list of copies
        demand: list[str] = []
        for s, k in slot_require.items():
            k = int(k)
            if k > 0:
                demand.extend([s] * k)
        if not demand:
            return (0, 0)

        # Map emp -> skill set
        emp_sk: dict[int, set[str]] = {}
        for e in assigned:
            sk = staff_skills[e]
            if isinstance(sk, dict):
                emp_sk[e] = {s for s, ok in sk.items() if ok}
            else:
                emp_sk[e] = set(sk)

        # Greedy: rarer skills first
        from collections import Counter

        rarity = Counter(demand)
        wanted = sorted(demand, key=lambda s: rarity[s])

        covered = 0
        used: set[int] = set()
        for s in wanted:
            chosen = next(
                (e for e in assigned if e not in used and s in emp_sk[e]), None
            )
            if chosen is not None:
                used.add(chosen)
                covered += 1

        # unmatched on-demand = assigned workers who didn't match any demanded skill
        unmatched = len(assigned) - covered
        return (covered, unmatched)

    # --------- metrics ---------

    def compute_coverage_metrics(self, res: Any, data: Any) -> CoverageMetrics:
        """
        Compute metrics with explicit definitions (see CoverageMetrics).
        """
        D, H = int(self.cfg.DAYS), int(self.cfg.HOURS)
        req_grid = self._slot_requirements()
        per_slot = self._assigned_sets(res)

        # prepare staff_skills[e]
        staff_skills: list[dict[str, bool] | set[str]] = []
        for st in data.staff:
            sk = getattr(st, "skills", None)
            if isinstance(sk, dict):
                staff_skills.append({k: bool(v) for k, v in sk.items()})
            elif sk is not None:
                try:
                    staff_skills.append(set(sk))
                except TypeError:
                    staff_skills.append(set())
            else:
                # legacy attributes like skillA/skillB can be normalized by caller if needed
                staff_skills.append(set())

        skill_demand_hours = 0
        people_hour_lower_bound = 0
        assigned_people_hours = 0
        assignment_hours_on_demanded_slots = 0
        assignment_hours_in_zero_demand_slots = 0
        covered_skill_copies = 0
        unmatched_on_demand = 0

        for d in range(D):
            for h in range(H):
                r = req_grid[d][h]
                people_hour_lower_bound += int(r.required_people_for_slot)
                ssum = sum(int(v) for v in r.per_skill_minima.values())
                skill_demand_hours += ssum

                assigned = sorted(per_slot.get((d, h), set()))
                assigned_people_hours += len(assigned)

                if ssum > 0:
                    assignment_hours_on_demanded_slots += len(assigned)
                    cov, un = self._greedy_cover(
                        assigned, r.per_skill_minima, staff_skills
                    )
                    covered_skill_copies += cov
                    unmatched_on_demand += un
                else:
                    assignment_hours_in_zero_demand_slots += len(assigned)

        return CoverageMetrics(
            skill_demand_hours=skill_demand_hours,
            people_hour_lower_bound=people_hour_lower_bound,
            assigned_people_hours=assigned_people_hours,
            assignment_hours_on_demanded_slots=assignment_hours_on_demanded_slots,
            assignment_hours_in_zero_demand_slots=assignment_hours_in_zero_demand_slots,
            covered_skill_copies=covered_skill_copies,
            unmatched_assignments_on_demand=unmatched_on_demand,
        )

    def compute_slot_gaps(
        self, res: Any, data: Any, top: int = 15
    ) -> tuple[list[SlotGap], pd.DataFrame]:
        """
        For each (day, hour), compare:
          - required_people_for_slot (max skill minima)
          - assigned_people
          - available_people_upper_bound (allowed mask & not a holiday; ignores rest rules)
        Return sorted top gaps (unattainable first, then biggest deficit), and the full DataFrame.
        """
        D, H = int(self.cfg.DAYS), int(self.cfg.HOURS)
        req_grid = self._slot_requirements()
        per_slot = self._assigned_sets(res)

        # available upper bound
        allowed = getattr(data, "allowed", None)  # shape (N, H) bools
        rows: list[SlotGap] = []

        for d in range(D):
            for h in range(H):
                r = req_grid[d][h]
                req = int(r.required_people_for_slot)
                assigned = len(per_slot.get((d, h), set()))
                # count employees who could work that hour (ignoring sequencing/rest constraints)
                avail = 0
                for e, st in enumerate(data.staff):
                    ok_hour = bool(allowed[e][h]) if allowed is not None else True
                    is_holiday = d in set(getattr(st, "holidays", []))
                    if ok_hour and not is_holiday:
                        avail += 1

                deficit = max(req - assigned, 0)
                unattainable = req > avail
                rows.append(
                    SlotGap(
                        day=d,
                        hour=h,
                        required_people_for_slot=req,
                        assigned_people=assigned,
                        available_people_upper_bound=avail,
                        deficit=deficit,
                        unattainable=unattainable,
                    )
                )

        df = pd.DataFrame([r.__dict__ for r in rows])
        df_pos = df[df["required_people_for_slot"] > 0]
        df_sorted = df_pos.sort_values(
            ["unattainable", "deficit", "required_people_for_slot"],
            ascending=[False, False, False],
        )
        top_rows = [
            SlotGap(**cast(dict, r))
            for r in df_sorted.head(top).to_dict(orient="records")
        ]
        return top_rows, df_sorted

    # ----------------------------- Rendering -----------------------------

    def render_text_report(self, res: Any, data: Any) -> None:
        """
        Print a readable report with clarified terminology.
        """
        status = self.adapter.status_name(res)
        obj = self.adapter.objective_value(res)
        avg_run = self.adapter.avg_consecutive_workday_run(res)
        max_run = self.adapter.max_consecutive_workday_run(res)

        print(f"Solver status: {status}")
        if status == "INFEASIBLE":
            print(
                "No feasible schedule found. If your solver exposes UNSAT cores/groups, show them here."
            )
            return
        if obj is None:
            print("No trusted solution; exiting.")
            return

        # Employee summary
        df_emp = self.adapter.df_emp(res)
        if not df_emp.empty and "hours" in df_emp.columns:
            print(f"\nPer-employee hours (top {self.num_print_examples}):")
            print(df_emp.head(self.num_print_examples).to_string(index=False))

            hrs = pd.to_numeric(df_emp["hours"], errors="coerce").to_numpy(dtype=float)
            hrs = hrs[~np.isnan(hrs)]
            if hrs.size:
                mean = float(np.mean(hrs))
                std = float(np.std(hrs, ddof=1)) if hrs.size > 1 else float("nan")
                p5, p95 = (
                    np.percentile(hrs, [5.0, 95.0])
                    if hrs.size > 1
                    else (float(hrs.min()), float(hrs.max()))
                )
                mn, mx = float(np.min(hrs)), float(np.max(hrs))
                print(
                    "\nHours distribution across employees: "
                    f"mean={self._fmt_float(mean)} | std={self._fmt_float(std)} | "
                    f"p5={self._fmt_float(p5)} | p95={self._fmt_float(p95)} | "
                    f"min={self._fmt_float(mn)} | max={self._fmt_float(mx)}"
                )

            cap = getattr(self.cfg, "WEEKLY_MAX_HOURS", None)
            if cap is not None:
                over = df_emp[pd.to_numeric(df_emp["hours"], errors="coerce") > cap]
                if not over.empty:
                    print(f"\n⚠️ Employees over cap {cap}h:")
                    print(over.to_string(index=False))
                else:
                    print(f"\nAll employees within weekly cap ({cap}h).")

        # Shift consistency (kept minimal for brevity)
        df_shifts = self.adapter.df_shifts(res)
        if not df_shifts.empty:
            df = df_shifts.copy()
            # minimal stats
            print("\nShift consistency (means across employees):")
            # reconstruct start_hour/duration where available
            if "start_hour" in df.columns and "length_h" in df.columns:
                g = df.groupby("employee_id", sort=False)
                start_std = g["start_hour"].std(ddof=1).mean()
                dur_mean = g["length_h"].mean().mean()
                dur_std = g["length_h"].std(ddof=1).mean()
                print(
                    f"duration mean={self._fmt_float(float(dur_mean))} | "
                    f"duration std≈{self._fmt_float(float(dur_std))} | "
                    f"start_hour std≈{self._fmt_float(float(start_std))}"
                )

        # Coverage metrics with clarified naming
        cov = self.compute_coverage_metrics(res, data)
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
                cov.covered_skill_copies / cov.skill_demand_hours
                if cov.skill_demand_hours > 0
                else 0.0
            )
            print(
                f"Skill coverage: covered_skill_copies = {cov.covered_skill_copies:,} / "
                f"skill_demand_hours = {cov.skill_demand_hours:,} "
                f"({self._fmt_float(coverage_ratio, nd=1, as_pct=True)})"
            )
            if cov.unmatched_assignments_on_demand > 0:
                print(
                    f"Unmatched on-demand assignments (people scheduled in demanded hours who could"
                    f" not cover any required skill): {cov.unmatched_assignments_on_demand:,}"
                )
            if cov.assignment_hours_in_zero_demand_slots > 0:
                print(
                    f"Assignments in zero-demand slots: {cov.assignment_hours_in_zero_demand_slots:,}"
                )
        else:
            print("Skill coverage: (no per-skill minima configured)")

        if avg_run is not None:
            print(
                "\nAvg consecutive days worked = " f"{self._fmt_float(float(avg_run))}"
            )
        if max_run is not None:
            print("Max consecutive days worked = " f"{self._fmt_float(float(max_run))}")

        # Objective value
        obj = self.adapter.objective_value(res)
        print(f"\nObjective value (overall penalty): {obj:,.0f}")

        # Slot gaps
        top_gaps, df_gaps = self.compute_slot_gaps(res, data, top=5)

        # Only care about rows where there is an actual problem (deficit>0) or unattainable
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

        # Hours histogram (reading from df_emp if present)
        self._print_hours_histogram(df_emp=self.adapter.df_emp(res))
        self._show_hour_of_day_histograms(res, data, enable_plot=True)

    # ----------------------------- Extras -----------------------------

    def _print_hours_histogram(self, df_emp: pd.DataFrame) -> None:
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
        _h = top.index.to_numpy(dtype=int)
        _n = top.to_numpy(dtype=int)
        modes = ", ".join(f"{h}h ({n})" for h, n in zip(_h, _n))
        print(f"\nMost common staff totals: {modes}")

    def _avg_staffing_by_hour_and_skill(
        self,
        res: SolveResult,
        data: InputData,
    ) -> tuple[pd.Series, dict[str, pd.Series]]:
        """
        Compute average staffing by hour-of-day across the horizon.

        Returns:
        overall_avg: pd.Series indexed by hour 0..H-1 -> average #employees working at that hour (averaged over days)
        per_skill_avg: dict[skill -> pd.Series indexed by hour 0..H-1] counting only employees who *have* that skill

        Notes:
        - Skills are taken *only* from self.cfg.SKILL_MIN (union of all keys in the grid).
        - Staff.skills may be a set[str] or dict[str, bool]; legacy attr fallback supported.
        - Uses the same hour grid as SKILL_MIN (H = self.cfg.HOURS).
        """
        C = self.cfg
        D, H = int(C.DAYS), int(C.HOURS)

        # Build {(day, hour) -> set(employee_id)} on the SKILL_MIN grid
        per_slot_sets = self._assigned_sets(res)

        # Derive skills solely from SKILL_MIN
        skills: set[str] = set()
        skill_min = getattr(C, "SKILL_MIN", None) or {}
        for d in range(D):
            for h in range(H):
                slot = skill_min[d][h] or {}
                skills.update(slot.keys())
        skills = {s for s in skills if s is s != "ANY"}  # drop empty skill names if any
        skills_order = sorted(skills)

        # Accumulators
        overall_counts = [0] * H
        per_skill_counts: dict[str, list[int]] = {s: [0] * H for s in skills_order}

        def _emp_has_skill(e: int, skill: str) -> bool:
            st = data.staff[e]
            sk = getattr(st, "skills", None)
            if isinstance(sk, dict):
                return bool(sk.get(skill, False))
            if sk is not None:
                try:
                    return skill in sk
                except TypeError:
                    return False
            # legacy attribute fallback: skillA / A / etc.
            return bool(getattr(st, f"skill{skill}", getattr(st, skill, False)))

        # Sum per hour-of-day across all days
        for d in range(D):
            for h in range(H):
                emps = per_slot_sets.get((d, h), set())
                n = len(emps)
                overall_counts[h] += n
                if n and skills_order:
                    for s in skills_order:
                        per_skill_counts[s][h] += sum(
                            1 for e in emps if _emp_has_skill(e, s)
                        )

        # Average across days
        if D > 0:
            overall_avg = pd.Series([c / D for c in overall_counts], index=range(H))
            per_skill_avg = {
                s: pd.Series([c / D for c in per_skill_counts[s]], index=range(H))
                for s in skills_order
            }
        else:
            overall_avg = pd.Series([0.0] * H, index=range(H))
            per_skill_avg = {
                s: pd.Series([0.0] * H, index=range(H)) for s in skills_order
            }

        return overall_avg, per_skill_avg

    def _show_hour_of_day_histograms(
        self,
        res: SolveResult,
        data: InputData,
        enable_plot: bool = True,
    ) -> None:
        """
        If enable_plot=True, makes a stacked bar chart of skills across hours of day (avg rates of provision)
        , with a black line representing avg number of staff working then.
        """
        overall, per_skill = self._avg_staffing_by_hour_and_skill(res, data)

        # Optional plotting to file (no GUI)
        if not enable_plot or not per_skill:
            return

        import matplotlib.cm as cm

        hours = list(overall.index)

        # Prepare soft, faint colours for bars
        # Use a pastel colormap; cycle if more skills than base colors
        cmap = cm.get_cmap("Pastel1")
        skills = list(per_skill.keys())
        colors = [cmap(i % cmap.N) for i in range(len(skills))]

        # Build stacked bars
        bottom = [0.0] * len(hours)
        fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
        for i, (s, series) in enumerate(per_skill.items()):
            vals = [float(series.loc[h]) for h in hours]
            ax.bar(
                hours,
                vals,
                bottom=bottom,
                label=s,
                color=colors[i],
                alpha=0.8,  # fainter
                width=0.9,
                edgecolor="none",
            )
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xlim(-0.5, len(hours) - 0.5)  # <- half-unit margin avoids clipping

        # Overlay total line in black
        ax.plot(
            hours,
            [float(overall.loc[h]) for h in hours],
            linewidth=2.5,
            color="black",
            label="Staff",
        )

        ax.set_xlabel("Hour of day")
        ax.set_ylabel("Avg num SKILLS covered")
        ax.set_xticks(hours)
        ax.legend(title="Skill", ncol=2)
        fig.tight_layout()
        plt.show()

    def _prompt_yes_no_default_yes(self, msg: str) -> bool:
        """
        Prompt the user '[Y/n]' and return True for yes (default on empty input),
        False for explicit 'n'/'no'. In non-interactive (no TTY), defaults to True.
        """
        try:
            if not sys.stdin or not sys.stdin.isatty():
                print(f"{msg} [Y/n] (non-interactive -> default: Y)")
                return True

            while True:
                resp = input(f"{msg} [Y/n]: ").strip().lower()
                if resp in ("", "y", "yes"):
                    return True
                if resp in ("n", "no"):
                    return False
                print("Please type 'y' or 'n'.")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted by user.")
            return False

        # ---------- Back-compat entry points (keep your old call sites) ----------

    def pre_solve(self, model: object) -> None:
        """
        Optional pre-solve check. If your model exposes `precheck()`, we’ll print:
          - capacity vs headcount lower bound
          - sample of per-skill shortfalls by (day,hour)
        If infeasible, require the user to confirm to continue (default: Yes).
        """
        precheck = getattr(model, "precheck", None)
        if not callable(precheck):
            print("Pre-check: (model has no `precheck()`; skipping)")
            return

        cap, dem, ok_cap, buckets, skill_stats = precheck()
        print_precheck_header(cap, dem, ok_cap)
        print_skill_status(
            buckets,
            stats=skill_stats,
            examples_per_skill=getattr(self.cfg, "PRINT_PRECHECK_EXAMPLES", 3),
        )

        if not ok_cap:
            proceed = self._prompt_yes_no_default_yes(
                "Pre-check indicates infeasibility. Continue anyway?"
            )
            if not proceed:
                raise SystemExit("Stopped by user after infeasible pre-check.")
        # --- require confirmation if infeasible ---
        if not ok_cap:
            proceed = self._prompt_yes_no_default_yes(
                "Pre-check indicates infeasibility. Continue anyway?"
            )
            if not proceed:
                raise SystemExit("Stopped by user after infeasible pre-check.")

    def post_solve(self, res: object, data: object) -> None:
        """
        Post-solve reporting (text). Delegates to the clarified, refactored report.
        """
        self.render_text_report(res, data)
