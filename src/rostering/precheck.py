# rostering/precheck.py
from __future__ import annotations

from typing import Set, Tuple

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


def precheck_availability(
    cfg: Config, data: InputData
) -> Tuple[int, int, bool, dict[str, list[Tuple[int, int, int]]]]:
    """
    cap: N * MAX_SHIFT_H
    dem: sum over (d,h) of max(SKILL_MIN[d][h].values(), default=0)
    buckets[skill]: list of (d,h,available_with_skill) where availability < required
    """
    cap = int(cfg.N * cfg.MAX_SHIFT_H)

    skills_required = sorted(_skills_in_min(cfg))
    buckets: dict[str, list[Tuple[int, int, int]]] = {s: [] for s in skills_required}

    # Allowed mask safeguard
    allowed = getattr(data, "allowed", None)
    if allowed is None or not np.any(allowed):
        allowed_mask = np.ones((cfg.N, cfg.HOURS), dtype=bool)
    else:
        allowed_mask = np.asarray(allowed, dtype=bool)
        assert allowed_mask.shape == (cfg.N, cfg.HOURS)

    # Narrow SKILL_MIN once for safe indexing
    skill_min = getattr(cfg, "SKILL_MIN", None)

    dem = 0
    for d in range(cfg.DAYS):
        for h in range(cfg.HOURS):
            if skill_min is not None:
                slot_min: dict[str, int] = dict(skill_min[d][h])
            else:
                slot_min = {}

            # skill-agnostic lower bound for headcount
            dem += int(max(slot_min.values())) if slot_min else 0

            # availability per skill = number of available staff whose skills contain that label
            if skills_required:
                avail_by_skill = {s: 0 for s in skills_required}
                for e in range(cfg.N):
                    st = data.staff[e]
                    if (d in getattr(st, "holidays", set())) or (
                        not allowed_mask[e, h]
                    ):
                        continue
                    for skill in slot_min.keys():
                        # Staff.skills is list[str]
                        if skill in getattr(st, "skills", ()):
                            avail_by_skill[skill] += 1

                # record shortfalls
                for skill, kmin in slot_min.items():
                    have = avail_by_skill.get(skill, 0)
                    if have < int(kmin):
                        buckets[skill].append((d, h, have))

    ok_cap = cap >= dem
    return cap, dem, ok_cap, buckets
