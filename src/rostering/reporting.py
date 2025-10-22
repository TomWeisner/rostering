from __future__ import annotations

from dataclasses import MISSING
from dataclasses import Field as DataclassField  # <-- add this
from typing import Sequence

import numpy as np
import pandas as pd

from rostering.config import Config
from rostering.data import InputData
from rostering.generate.staff import Staff
from rostering.result_types import SolveResult

BucketItem = tuple[int, int, int]
Buckets = dict[str, list[BucketItem]]  # <- dict keyed by skill


class Reporter:
    def __init__(self, cfg: Config) -> None:
        self.cfg: Config = cfg
        self.num_print_examples = 6

    @staticmethod
    def _fmt_float(x, nd: int = 2, as_pct: bool = False) -> str:
        try:
            if pd.isna(x):
                return "nan"
            if as_pct:
                return f"{float(100*x):.{nd}f}%"
            else:
                return f"{float(x):.{nd}f}"
        except Exception:
            return "nan"

    @staticmethod
    def _has_skill(s: object, name: str) -> bool:
        """Robust skill check: supports Staff.skills as set[str] or dict[str,bool],
        with a legacy fallback to attributes like 'skillA'."""
        if hasattr(s, "skills"):
            sk = getattr(s, "skills")
            if isinstance(sk, dict):
                return bool(sk.get(name, False))
            try:
                return name in sk  # set/list-like
            except TypeError:
                pass
        # legacy attribute fallback
        return bool(getattr(s, f"skill{name}", getattr(s, name, False)))

    def _coerce_inspect_ids(self) -> list[int]:
        """Turn cfg.INSPECT_EMPLOYEE_IDS into a list[int] even if it's a dataclass Field,
        scalar, None, etc."""
        ids = getattr(self.cfg, "INSPECT_EMPLOYEE_IDS", [])
        # If user mistakenly set a dataclasses.Field on the instance:
        if isinstance(ids, DataclassField):
            if ids.default is not MISSING:
                ids = ids.default
            elif ids.default_factory is not MISSING:  # type: ignore[attr-defined]
                ids = ids.default_factory()  # type: ignore[call-arg]
            else:
                ids = []
        if ids is None:
            return []
        if isinstance(ids, (list, tuple)):
            return [int(x) for x in ids]
        # scalar fallback
        try:
            return [int(ids)]
        except Exception:
            return []

    def _print_precheck(
        self, cap: int, dem: int, ok_cap: bool, buckets: Buckets
    ) -> None:
        """
        cap: N * MAX_SHIFT_H
        dem: sum over all (d,h) of max(SKILL_MIN[d][h].values(), default=0)
        buckets: {skill -> [(d,h,available_count) ...]} for skills that appear in SKILL_MIN
        """
        print(
            f"\nPre-check: cap={cap} (N*MAX_SHIFT_H) vs dem={dem} "
            f"(sum max per-slot minima) | OK={ok_cap}"
        )

        for skill in sorted(buckets.keys()):
            lst = buckets[skill]
            if not lst:
                continue
            examples = ", ".join(
                f"d={d},h={h:02d} (have {v})"
                for d, h, v in lst[: self.cfg.PRINT_PRECHECK_EXAMPLES]
            )
            print(f"- {skill} below min: {len(lst)} hours (e.g. {examples})")

    def _print_unsat_core(self, groups: dict[str, list[str]]) -> None:
        if not groups:
            print("No UNSAT core available (search or build does not support it).")
            return
        print("Unsat core (grouped):")
        for key, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            sample = ", ".join(sorted(items)[:5])
            more = f" (+{len(items)-5} more)" if len(items) > 5 else ""
            print(f"- {key}: {len(items)}; e.g. {sample}{more}")

    def _print_summary(self, res: SolveResult) -> None:
        required = min_required_person_hours(self.cfg)
        print(f"\nSummary: assignments={len(res.df_sched):,} | required={required:,}")
        print(f"\nAvg run length over worked days: {res.avg_run:.2f}")
        if res.objective_value is not None:
            print(f"Objective value (overall penalty): {res.objective_value:,.0f}")

    def _print_per_employee_cap(self, df_emp: pd.DataFrame) -> None:
        cfg = self.cfg
        print(f"\nPer-employee hours (top {self.num_print_examples}):")
        print(df_emp.head(self.num_print_examples).to_string(index=False))

        hrs_s: pd.Series = pd.to_numeric(df_emp["hours"], errors="coerce")
        hrs: np.ndarray = hrs_s.to_numpy(dtype=float)
        hrs = hrs[~np.isnan(hrs)]

        if hrs.size:
            mean = float(np.mean(hrs))
            std = float(np.std(hrs, ddof=1)) if hrs.size > 1 else float("nan")
            if hrs.size > 1:
                p5, p95 = np.percentile(hrs, [5.0, 95.0])
            else:
                p5, p95 = (float(hrs.min()), float(hrs.max()))
            mn, mx = float(np.min(hrs)), float(np.max(hrs))
            print(
                "\nHours distribution across employees: "
                f"mean={self._fmt_float(mean)} | std={self._fmt_float(std)} | "
                f"p5={self._fmt_float(p5)} | p95={self._fmt_float(p95)} | "
                f"min={self._fmt_float(mn)} | max={self._fmt_float(mx)}"
            )

        if cfg.WEEKLY_MAX_HOURS is not None:
            over_cap = df_emp[df_emp["hours"] > cfg.WEEKLY_MAX_HOURS]
            if not over_cap.empty:
                print(f"\n⚠️ Employees over cap {cfg.WEEKLY_MAX_HOURS}h:")
                print(over_cap.to_string(index=False))
            else:
                print(f"\nAll employees within weekly cap ({cfg.WEEKLY_MAX_HOURS}h).")

    def _print_shift_consistency(self, res: SolveResult) -> list[int]:
        df = res.df_shifts.copy()
        if df.empty:
            print("\nShift consistency: (no shifts)")
            return []

        df["start_hour"] = pd.to_numeric(df["start_hour"], errors="coerce").astype(
            float
        )
        dur_series = pd.to_numeric(df["model_length_h"], errors="coerce")
        df["duration_h"] = dur_series.astype(float)
        df["dow"] = pd.to_datetime(df["start_date"]).dt.dayofweek

        agg_df = df.groupby("employee_id", sort=False).agg(
            n_shifts=("start_hour", "size"),
            start_hour_mean=("start_hour", "mean"),
            start_hour_std=("start_hour", lambda s: s.std(ddof=1)),
            duration_mean=("duration_h", "mean"),
            duration_std=("duration_h", lambda s: s.std(ddof=1)),
            dow_distinct=("dow", "nunique"),
        )

        vc_dow = df.groupby("employee_id")["dow"].value_counts(
            normalize=True, dropna=False
        )
        dow_modal_idx = vc_dow.groupby(level=0).idxmax()
        dow_modal = dow_modal_idx.map(lambda t: t[1])
        dow_modal_rate = vc_dow.groupby(level=0).max()

        vc_hour = df.groupby("employee_id")["start_hour"].value_counts(
            normalize=True, dropna=False
        )
        hour_modal_idx = vc_hour.groupby(level=0).idxmax()
        hour_modal = hour_modal_idx.map(lambda t: float(t[1]))
        hour_modal_rate = vc_hour.groupby(level=0).max()

        per_emp = agg_df.join(
            pd.DataFrame(
                {
                    "dow_modal": dow_modal,
                    "dow_modal_rate": dow_modal_rate,
                    "hour_modal": hour_modal,
                    "hour_modal_rate": hour_modal_rate,
                }
            ),
            how="left",
        ).reset_index()

        def _safe_mean(s: pd.Series) -> float:
            s = pd.to_numeric(s, errors="coerce")
            return float(s.mean())

        print("\nShift consistency — per-employee summary (means across employees):")
        print(
            "duration mean="
            f"{self._fmt_float(_safe_mean(per_emp['duration_mean']))} | "
            "duration std≈"
            f"{self._fmt_float(_safe_mean(per_emp['duration_std']))} | "
            "start_hour std≈"
            f"{self._fmt_float(_safe_mean(per_emp['start_hour_std']))} | "
            "modal start-hour rate="
            f"{self._fmt_float(_safe_mean(per_emp['hour_modal_rate']), nd=1, as_pct=True)} | "
            "distinct DOW≈"
            f"{self._fmt_float(_safe_mean(per_emp['dow_distinct']))} | "
            "modal DOW rate="
            f"{self._fmt_float(_safe_mean(per_emp['dow_modal_rate']), nd=1, as_pct=True)}"
        )

        show = per_emp.sort_values("start_hour_std", ascending=False).head(
            self.num_print_examples
        )
        cols = [
            "employee_id",
            "n_shifts",
            "start_hour_mean",
            "start_hour_std",
            "duration_mean",
            "duration_std",
            "dow_distinct",
            "dow_modal",
            "dow_modal_rate",
            "hour_modal",
            "hour_modal_rate",
        ]
        print(f"\nMost variable start-hour employees (top {self.num_print_examples}):")
        print(show[cols].to_string(index=False, float_format=lambda x: f"{x:0.2f}"))
        employee_ids = [
            int(x) for x in show["employee_id"].iloc[: self.num_print_examples]
        ]
        print("Variable employee_ids", employee_ids)
        return employee_ids

    def _print_shift_aware(
        self,
        res: SolveResult,
        staff: Sequence[Staff],
        inspect_ids: Sequence[int],
    ) -> None:
        def fmt_h(h: float) -> str:
            return f"{int(h):02d}:00"

        if not inspect_ids:
            return
        print("\nDetailed shifts for selected employees:")
        df = res.df_shifts
        for ee in inspect_ids:
            s = staff[ee]
            df_e = df[df["employee_id"] == ee]
            print(
                f"\nEmployee id={ee} | {s.name} | band={s.band} | "
                f"A={int(self._has_skill(s, 'A'))} | B={int(self._has_skill(s, 'B'))} | "
                f"night={int(getattr(s,'is_night_worker',0))}"
            )
            if df_e.empty:
                print("  (no shifts assigned)")
                continue

            sh_mean = float(df_e["start_hour"].mean())
            sh_std = float(df_e["start_hour"].std(ddof=1))
            dur = pd.to_numeric(df_e["model_length_h"], errors="coerce")
            d_mean = float(dur.mean())
            d_std = float(dur.std(ddof=1))
            dow = pd.to_datetime(df_e["start_date"]).dt.dayofweek
            mode_series = dow.mode()
            dow_mode = int(mode_series.iat[0]) if not mode_series.empty else np.nan
            dow_share = (dow == dow_mode).mean() if not np.isnan(dow_mode) else np.nan

            print(
                "  Stats: "
                f"start_hour mean={self._fmt_float(sh_mean)} "
                f"std={self._fmt_float(sh_std)} | "
                f"duration mean={self._fmt_float(d_mean)} "
                f"std={self._fmt_float(d_std)} | "
                f"modal DOW={dow_mode if not pd.isna(dow_mode) else 'nan'} "
                f"(share={self._fmt_float(dow_share)})"
            )

            total_shift_hours = 0
            for _, row in df_e.sort_values(["start_date", "start_hour"]).iterrows():
                start_date = row["start_date"]
                end_date = row["end_date"]
                sh = int(row["start_hour"])
                eh = int(row["end_hour"])
                Lh = int(row["model_length_h"])
                total_shift_hours += Lh
                if start_date == end_date:
                    print(f"  {start_date}  {fmt_h(sh)} → {fmt_h(eh)} (model L={Lh}h)")
                else:
                    print(
                        f"  {start_date}  {fmt_h(sh)} → {end_date} {fmt_h(eh)} (model L={Lh}h)"
                    )
            print(f"  Total hours for employee {ee}: {total_shift_hours}")

    # ---------- public API ----------
    def pre_solve(self, model: object) -> None:
        cap, dem, ok_cap, buckets = getattr(model, "precheck")()
        self._print_precheck(cap, dem, ok_cap, buckets)

    def post_solve(
        self,
        res: SolveResult,
        data: InputData,
    ) -> None:
        print("Solver status:", res.status_name)
        if res.status_name == "INFEASIBLE":
            self._print_unsat_core(res.unsat_core_groups)
            return
        if res.objective_value is None:
            print("No trusted solution; exiting.")
            return

        self._print_per_employee_cap(res.df_emp)
        variable_employees = self._print_shift_consistency(res)
        base_ids = self._coerce_inspect_ids()
        self._print_shift_aware(res, data.staff, base_ids + variable_employees[:3])
        self._print_summary(res)


def min_required_person_hours(C: Config) -> int:
    """
    Skill-agnostic lower bound on total person-hours required by SKILL_MIN:
    For each (d,h), take the largest single-skill minimum in that slot.
    """
    days = int(getattr(C, "DAYS", 0))
    hours = int(getattr(C, "HOURS", 0))
    total = 0
    skill_min = getattr(C, "SKILL_MIN", None)
    if skill_min is None:
        return 0

    for d in range(days):
        for h in range(hours):
            slot_min = skill_min[d][h]
            slot_need = max(slot_min.values()) if slot_min else 0
            total += int(slot_need)
    return total
