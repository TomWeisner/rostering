# rostering/precheck.py
from __future__ import annotations

from typing import Tuple

from rostering.config import Config
from rostering.data import InputData


def precheck_availability(
    cfg: Config, data: InputData
) -> Tuple[int, int, bool, tuple[list, list, list, list]]:
    """
    Quick necessary-condition check before building the CP model.
    Counts per-hour availability upper bounds ignoring contiguity/rest.
    """
    cap = cfg.N * cfg.MAX_SHIFT_H
    dem = cfg.COVER * cfg.HOURS
    ok_cap = cap >= dem

    few_cover: list[tuple] = []
    few_sen: list[tuple] = []
    few_A: list[tuple] = []
    few_B: list[tuple] = []

    for d in range(cfg.DAYS):
        for h in range(cfg.HOURS):
            avail = senior = a = b = 0
            for e in range(cfg.N):
                s = data.staff[e]
                if (
                    (d in s.holidays)
                    or (d in cfg.PUBLIC_HOLIDAYS)
                    or (not data.allowed[e][h])
                ):
                    continue
                avail += 1
                if s.band >= 2:
                    senior += 1
                if s.skillA:
                    a += 1
                if s.skillB:
                    b += 1

            if avail < cfg.COVER:
                few_cover.append((d, h, avail))
            if senior < cfg.MIN_SENIOR:
                few_sen.append((d, h, senior))
            if a < cfg.MIN_SKILL_A:
                few_A.append((d, h, a))
            if b < cfg.MIN_SKILL_B:
                few_B.append((d, h, b))

    return cap, dem, ok_cap, (few_cover, few_sen, few_A, few_B)
