# rostering/precheck.py
from __future__ import annotations

import sys
from typing import Dict, List, Set, Tuple

import numpy as np

from rostering.config import Config
from rostering.data import InputData


def _skills_in_min(C: Config) -> Set[str]:
    out: Set[str] = set()
    skill_min = getattr(C, "SKILL_MIN", None)
    if skill_min is None:
        return out
    for row in skill_min:
        for slot in row:
            out.update(slot.keys())
    return out


def _people_hour_lower_bound(cfg: Config) -> int:
    """Sum over (d,h) of max_s SKILL_MIN[d][h][s]. Headcount-only lower bound."""
    skill_min = getattr(cfg, "SKILL_MIN", None)
    if skill_min is None:
        return 0
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


def precheck_availability(cfg: Config, data: InputData) -> Tuple[
    int,  # cap
    int,  # dem
    bool,  # ok_cap
    Dict[str, List[Tuple[int, int, int]]],  # buckets
    Dict[str, Dict[str, int]],  # skill_stats
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
          'shortfall_slots': #slots where available < required
      }
    """
    # Capacity vs lower bound
    cap = _capacity_upper_bound_people_hours(cfg, data)
    dem = _people_hour_lower_bound(cfg)
    ok_cap = cap >= dem

    # Setup
    N, D, H = int(cfg.N), int(cfg.DAYS), int(cfg.HOURS)
    skills_required = sorted(_skills_in_min(cfg))
    buckets: Dict[str, List[Tuple[int, int, int]]] = {s: [] for s in skills_required}
    skill_stats: Dict[str, Dict[str, int]] = {
        s: {
            "required": 0,
            "available": 0,
            "min_slack": 10**9,
            "tight_slots": 0,
            "shortfall_slots": 0,
        }
        for s in skills_required
    }

    allowed = getattr(data, "allowed", None)
    if allowed is None:
        allowed_mask = np.ones((N, H), dtype=bool)
    else:
        allowed_mask = np.asarray(allowed, dtype=bool)
        assert allowed_mask.shape == (N, H)

    skill_min = getattr(cfg, "SKILL_MIN", None) or {}

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

    return cap, dem, ok_cap, buckets, skill_stats


def print_precheck_header(cap: int, dem: int, ok_cap: bool) -> None:
    """Print 'Pre-check' on its own line, then capacity line with ✅/❌"""
    print("\nPre-check:\n")
    if ok_cap:
        print(f"✅ Capacity = {cap:,} | people_hour_lower_bound = {dem:,} | OK")
    else:
        print(f"❌ Capacity = {cap:,} | people_hour_lower_bound = {dem:,} | NOT OK")


def print_skill_status(
    buckets: Dict[str, List[Tuple[int, int, int]]],
    *,
    stats: Dict[str, Dict[str, int]],
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

        suffix = f" | requires {st['required']:,}, have {st['available']:,}"
        if st["required"] > 0:
            suffix += f" (min slack {st['min_slack']}, tight {st['tight_slots']})"

        if not slots:
            print(f"✅ {skill} — satisfied{suffix}", file=stream)
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
