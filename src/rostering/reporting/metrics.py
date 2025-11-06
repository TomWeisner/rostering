from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Sequence, cast

import pandas as pd

from rostering.input_data import InputData

from .adapters import ResultAdapter
from .data_models import CoverageMetrics, SlotGap, SlotRequirement


def slot_requirements(cfg: Any) -> list[list[SlotRequirement]]:
    """Build a grid of SlotRequirement from cfg.SKILL_MIN."""
    D, H = int(cfg.DAYS), int(cfg.HOURS)
    skill_min = getattr(cfg, "SKILL_MIN", None) or {}
    grid: list[list[SlotRequirement]] = []
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
        grid.append(row)
    return grid


def assigned_sets(
    cfg: Any, res: Any, adapter: ResultAdapter
) -> dict[tuple[int, int], set[int]]:
    """Build {(day, hour) -> set(employee_id)} from schedule/shifts."""
    D, H = int(cfg.DAYS), int(cfg.HOURS)
    per_slot: dict[tuple[int, int], set[int]] = {}

    sched = adapter.df_sched(res)
    if not sched.empty:
        for _, r in sched.iterrows():
            d, h, e = int(r["day"]), int(r["hour"]), int(r["employee_id"])
            if 0 <= d < D and 0 <= h < H:
                per_slot.setdefault((d, h), set()).add(e)
        return per_slot

    shifts = adapter.df_shifts(res)
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


def _prepare_staff_skills(data: InputData) -> list[dict[str, bool] | set[str]]:
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
            staff_skills.append(set())
    return staff_skills


def _greedy_cover(
    assigned_emp_ids: Iterable[int],
    slot_require: dict[str, int],
    staff_skills: Sequence[dict[str, bool] | set[str]],
) -> tuple[int, int]:
    """Return (covered_skill_copies, unmatched_assignments_on_demand) for a slot."""
    assigned = list(assigned_emp_ids)
    if not assigned or not slot_require:
        return (0, 0)

    demand: list[str] = []
    for s, k in slot_require.items():
        k = int(k)
        if k > 0:
            demand.extend([s] * k)
    if not demand:
        return (0, 0)

    emp_sk: dict[int, set[str]] = {}
    for e in assigned:
        sk = staff_skills[e]
        if isinstance(sk, dict):
            emp_sk[e] = {s for s, ok in sk.items() if ok}
        else:
            emp_sk[e] = set(sk)

    rarity = Counter(demand)
    wanted = sorted(demand, key=lambda s: rarity[s])

    covered = 0
    used: set[int] = set()
    for s in wanted:
        chosen = next((e for e in assigned if e not in used and s in emp_sk[e]), None)
        if chosen is not None:
            used.add(chosen)
            covered += 1

    unmatched = len(assigned) - covered
    return covered, unmatched


def compute_coverage_metrics(
    cfg: Any, res: Any, data: InputData, adapter: ResultAdapter
) -> CoverageMetrics:
    """Compute CoverageMetrics for a solve result."""
    D, H = int(cfg.DAYS), int(cfg.HOURS)
    req_grid = slot_requirements(cfg)
    per_slot = assigned_sets(cfg, res, adapter)
    staff_skills = _prepare_staff_skills(data)

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
            slot_skill_total = sum(int(v) for v in r.per_skill_minima.values())
            skill_demand_hours += slot_skill_total

            assigned = sorted(per_slot.get((d, h), set()))
            assigned_people_hours += len(assigned)

            if slot_skill_total > 0:
                assignment_hours_on_demanded_slots += len(assigned)
                cov, un = _greedy_cover(assigned, r.per_skill_minima, staff_skills)
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
        covered_skills=covered_skill_copies,
        unmatched_assignments_on_demand=unmatched_on_demand,
    )


def compute_slot_gaps(
    cfg: Any,
    res: Any,
    data: InputData,
    adapter: ResultAdapter,
    top: int = 15,
) -> tuple[list[SlotGap], pd.DataFrame]:
    """Return top gap slots plus the full DataFrame of per-slot stats."""
    D, H = int(cfg.DAYS), int(cfg.HOURS)
    req_grid = slot_requirements(cfg)
    per_slot = assigned_sets(cfg, res, adapter)

    allowed = getattr(data, "allowed", None)
    rows: list[SlotGap] = []

    for d in range(D):
        for h in range(H):
            r = req_grid[d][h]
            req = int(r.required_people_for_slot)
            assigned = len(per_slot.get((d, h), set()))

            avail = 0
            for e, st in enumerate(data.staff):
                ok_hour = bool(allowed[e][h]) if allowed is not None else True
                holidays: set[int] = getattr(st, "holidays", set())
                is_holiday = d in cast(
                    set[int], holidays if isinstance(holidays, set) else set(holidays)
                )
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
        SlotGap(**cast(dict[str, Any], r))
        for r in df_sorted.head(top).to_dict(orient="records")
    ]
    return top_rows, df_sorted


def avg_staffing_by_hour_and_skill(
    cfg: Any,
    res: Any,
    data: InputData,
    adapter: ResultAdapter,
) -> tuple[pd.Series, dict[str, pd.Series]]:
    """Compute average staffing by hour-of-day (overall + per skill)."""
    D, H = int(cfg.DAYS), int(cfg.HOURS)
    per_slot_sets = assigned_sets(cfg, res, adapter)

    skills: set[str] = set()
    skill_min = getattr(cfg, "SKILL_MIN", None) or {}
    for d in range(D):
        for h in range(H):
            slot = skill_min[d][h] or {}
            skills.update(slot.keys())
    skills_order = sorted(sk for sk in skills if sk)

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
        return bool(getattr(st, f"skill{skill}", getattr(st, skill, False)))

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

    if D > 0:
        overall_avg = pd.Series([c / D for c in overall_counts], index=range(H))
        per_skill_avg = {
            s: pd.Series([c / D for c in per_skill_counts[s]], index=range(H))
            for s in skills_order
        }
    else:
        overall_avg = pd.Series([0.0] * H, index=range(H))
        per_skill_avg = {s: pd.Series([0.0] * H, index=range(H)) for s in skills_order}

    return overall_avg, per_skill_avg
