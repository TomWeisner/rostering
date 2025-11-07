# rostering/precheck.py
from __future__ import annotations

import sys
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

import numpy as np

from rostering.config import Config, SkillGrid
from rostering.input_data import InputData


def _skill_min_grid(cfg: Config) -> SkillGrid:
    """Return the SKILL_MIN grid (or an empty grid if none provided)."""
    skill_min: SkillGrid | None = getattr(cfg, "SKILL_MIN", None)
    if skill_min is None:
        D, H = int(cfg.DAYS), int(cfg.HOURS)
        return [[{} for _ in range(H)] for _ in range(D)]
    return skill_min


def _skills_in_min(cfg: Config) -> Set[str]:
    out: Set[str] = set()
    skill_min = _skill_min_grid(cfg)
    for row in skill_min:
        for slot in row:
            out.update(slot.keys())
    return out


def _people_hour_lower_bound(cfg: Config) -> int:
    """Sum over (d,h) of max_s SKILL_MIN[d][h][s]. Headcount-only lower bound."""
    skill_min = _skill_min_grid(cfg)
    dem = 0
    for d in range(int(cfg.DAYS)):
        for h in range(int(cfg.HOURS)):
            slot = skill_min[d][h] or {}
            dem += int(max(slot.values())) if slot else 0
    return dem


def _capacity_upper_bound_people_hours(cfg: Config, data: InputData) -> int:
    """
    Loose *upper bound* on total assignable person-hours over the horizon:

      cap = Σ_e min( available_hours_e , per_employee_hour_cap )

    where:
      available_hours_e = allowed hours per day (by hour-of-day mask) × (# workable days)
                          (holidays remove whole days for that employee)
      per_employee_hour_cap = WEEKLY_MAX_HOURS if set, else DAYS*HOURS (no explicit cap)

    Notes:
      - Ignores rest/sequence rules (OK for a precheck upper bound).
      - If `allowed` is None, assume all hours per day are allowed.
      - `allowed` shape is (N, HOURS), repeated each day.
    """
    N = int(cfg.N)
    D = int(cfg.DAYS)
    H = int(cfg.HOURS)

    weekly_cap = getattr(cfg, "WEEKLY_MAX_HOURS", None)
    horizon_cap = D * H
    per_emp_cap = int(weekly_cap) if weekly_cap is not None else horizon_cap

    allowed = getattr(data, "allowed", None)
    if allowed is None:
        allowed_mask = np.ones((N, H), dtype=bool)
    else:
        allowed_mask = np.asarray(allowed, dtype=bool)
        assert allowed_mask.shape == (N, H), "allowed must be shape (N, HOURS)"

    per_emp_allowed_per_day = allowed_mask.sum(axis=1)  # shape (N,)

    cap_total = 0
    for e in range(N):
        holidays_e: Set[int] = getattr(data.staff[e], "holidays", set())
        if not isinstance(holidays_e, set):
            holidays_e = set(holidays_e)
        workable_days = max(0, D - len(holidays_e))
        available_hours_e = int(per_emp_allowed_per_day[e]) * workable_days
        cap_total += min(available_hours_e, per_emp_cap)

    return cap_total


def _has_skill(st: object, skill: str) -> bool:
    sks = getattr(st, "skills", ())
    try:
        return skill in sks
    except TypeError:
        return False


def _skill_supply_counts(data: InputData, skills: Iterable[str]) -> Dict[str, int]:
    counts = {s: 0 for s in skills}
    if not counts:
        return counts
    for st in getattr(data, "staff", []):
        for s in counts.keys():
            if _has_skill(st, s):
                counts[s] += 1
    return counts


def _skill_hour_holes(
    data: InputData, skills: Sequence[str], allowed_mask: np.ndarray
) -> Dict[str, List[int]]:
    """
    For each skill, list hour-of-day indices where zero qualified staff are allowed to work.
    Holidays are ignored (we only look at structural availability).
    """
    H = allowed_mask.shape[1] if allowed_mask.size else 0
    staff = getattr(data, "staff", [])
    skill_to_emp: Dict[str, List[int]] = {
        s: [e for e, st in enumerate(staff) if _has_skill(st, s)] for s in skills
    }
    holes: Dict[str, List[int]] = {s: [] for s in skills}
    for s, idxs in skill_to_emp.items():
        if not idxs:
            # no staff possess this skill -> every hour is a structural hole
            holes[s] = list(range(H))
            continue
        for h in range(H):
            if not any(allowed_mask[e, h] for e in idxs):
                holes[s].append(h)
    return holes


def precheck_availability(
    cfg: Config,
    data: InputData,
    *,
    verbose: bool = True,
    examples_per_skill: int = 3,
    stream=None,
) -> Tuple[
    int,  # cap
    int,  # dem
    bool,  # ok_cap
    Dict[str, List[Tuple[int, int, int]]],  # buckets
    Dict[str, Dict[str, Any]],  # skill_stats
]:
    """
    Returns:
      cap: people-hour *upper bound* across the horizon
      dem: headcount lower bound (Σ max_s per-slot minima)
      ok_cap: cap >= dem
      buckets[skill]: list of (day, hour, available_with_skill) where availability < per-skill required
      skill_stats[skill]: {
          'required': sum of minima over demanded slots,
          'available': sum of available-with-skill over those slots,
          'min_slack': min over slots of (available - required),
          'tight_slots': #slots where available == required,
          'shortfall_slots': #slots where available < required,
          'staff_count': number of employees who possess this skill (any hour),
          'has_any_staff': bool flag mirroring staff_count > 0
      }
    If `verbose` is True, this function prints the header + per-skill status (including
    skills that have demand but zero qualified staff) using `stream`.
    """
    # Capacity vs lower bound
    cap = _capacity_upper_bound_people_hours(cfg, data)
    dem = _people_hour_lower_bound(cfg)
    ok_cap = cap >= dem
    stream = stream or sys.stdout

    # Setup
    N, D, H = int(cfg.N), int(cfg.DAYS), int(cfg.HOURS)
    skills_required = sorted(_skills_in_min(cfg))
    buckets: Dict[str, List[Tuple[int, int, int]]] = {s: [] for s in skills_required}
    skill_supply = _skill_supply_counts(data, skills_required)
    skill_stats: Dict[str, Dict[str, Any]] = {
        s: {
            "required": 0,
            "available": 0,
            "min_slack": 10**9,
            "tight_slots": 0,
            "shortfall_slots": 0,
            "staff_count": skill_supply.get(s, 0),
            "has_any_staff": skill_supply.get(s, 0) > 0,
        }
        for s in skills_required
    }

    allowed = getattr(data, "allowed", None)
    if allowed is None:
        allowed_mask = np.ones((N, H), dtype=bool)
    else:
        allowed_mask = np.asarray(allowed, dtype=bool)
        assert allowed_mask.shape == (N, H)

    skill_min = _skill_min_grid(cfg)
    hour_holes = _skill_hour_holes(data, skills_required, allowed_mask)

    # Single pass: build buckets and stats together
    for d in range(D):
        for h in range(H):
            slot_min = skill_min[d][h] or {}
            if not slot_min:
                continue

            # count availability by skill at (d,h)
            avail_by_skill: Dict[str, int] = {s: 0 for s in slot_min.keys()}
            for e in range(N):
                st = data.staff[e]
                if (d in getattr(st, "holidays", set())) or (not allowed_mask[e, h]):
                    continue
                for s in slot_min.keys():
                    if _has_skill(st, s):
                        avail_by_skill[s] += 1

            # update per-skill stats and buckets
            for s, req in slot_min.items():
                have = avail_by_skill.get(s, 0)

                # stats
                skill_stats[s]["required"] += int(req)
                skill_stats[s]["available"] += int(have)
                slack = int(have) - int(req)
                if slack < skill_stats[s]["min_slack"]:
                    skill_stats[s]["min_slack"] = slack
                if slack == 0:
                    skill_stats[s]["tight_slots"] += 1
                elif slack < 0:
                    skill_stats[s]["shortfall_slots"] += 1
                    buckets[s].append((d, h, have))

    # Normalize min_slack for skills that never appeared
    for s, dct in skill_stats.items():
        if dct["required"] == 0:
            dct["min_slack"] = 0

    if verbose:
        print_precheck_header(cap, dem, ok_cap)
        print_skill_status(
            buckets,
            stats=skill_stats,
            examples_per_skill=examples_per_skill,
            stream=stream,
        )
        print_skill_hour_holes(hour_holes, stream=stream)

    return cap, dem, ok_cap, buckets, skill_stats


def print_precheck_header(cap: int, dem: int, ok_cap: bool) -> None:
    """Print 'Pre-check' on its own line, then capacity line with ✅/❌"""
    print("\nPre-check:\n")
    if ok_cap:
        print(f"✅ Capacity = {cap:,} | people_hour_lower_bound = {dem:,} | OK")
    else:
        print(f"❌ Capacity = {cap:,} | people_hour_lower_bound = {dem:,} | NOT OK")
    print(
        "ℹ️  Pre-check only verifies raw capacity/skill availability; the fully solved model may still be infeasible if other constraints are violated."
    )


def print_skill_status(
    buckets: Dict[str, List[Tuple[int, int, int]]],
    *,
    stats: Dict[str, Dict[str, Any]],
    examples_per_skill: int = 3,
    stream=sys.stdout,
) -> None:
    """
    One line per skill using ✅/❌ only
    Shows: requires R, have A (min slack S; tight T). Examples for shortfalls.
    """
    for skill in sorted(buckets.keys()):
        slots = buckets.get(skill, [])
        st = stats.get(
            skill, {"required": 0, "available": 0, "min_slack": 0, "tight_slots": 0}
        )

        suffix = (
            f" | requires {st.get('required', 0):,}, have {st.get('available', 0):,}"
        )
        if st["required"] > 0:
            suffix += (
                f" (min slack={st['min_slack']} meaning worst-case available - required; "
                f"tight slots={st['tight_slots']} where available == required)"
            )
        staff_count = st.get("staff_count", 0)
        suffix += f" | staff with skill: {staff_count}"

        if not slots:
            print(f"✅ {skill} — satisfied{suffix}", file=stream)
            continue

        if not st.get("has_any_staff", True):
            n = len(slots)
            sample = ", ".join(
                f"d={d},h={h:02d}" for d, h, _ in slots[:examples_per_skill]
            )
            more = f", +{n - examples_per_skill} more" if n > examples_per_skill else ""
            print(
                f"❌ {skill} — demanded in {n} slot(s) but no employee has this skill"
                f"{(' — e.g. ' + sample + more) if sample else ''}"
                f"{suffix}",
                file=stream,
            )
            continue

        n = len(slots)
        sample = ", ".join(
            f"d={d},h={h:02d} (have {v})" for d, h, v in slots[:examples_per_skill]
        )
        more = f", +{n - examples_per_skill} more" if n > examples_per_skill else ""
        print(
            f"❌ {skill} — {n} shortfall slot(s)"
            f"{(' — e.g. ' + sample + more) if sample else ''}"
            f"{suffix}",
            file=stream,
        )


def print_skill_hour_holes(
    hour_holes: Dict[str, List[int]],
    *,
    stream=sys.stdout,
) -> None:
    """Report hour-of-day indices that lack any eligible staff per skill."""
    print("\nSkill/hour availability check:", file=stream)
    any_gap = any(hour_holes.get(skill) for skill in hour_holes)
    if not any_gap:
        print(
            "✅ Every skill has at least one eligible staff member for every hour.",
            file=stream,
        )
        return
    for skill in sorted(hour_holes.keys()):
        hours = hour_holes.get(skill, [])
        if not hours:
            continue
        sample = ", ".join(f"{h:02d}" for h in hours[:12])
        more = f", +{len(hours) - 12} more" if len(hours) > 12 else ""
        print(
            f"❌ {skill} — no eligible staff for hour(s): {sample}{more}",
            file=stream,
        )
