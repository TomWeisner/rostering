from __future__ import annotations

from typing import Callable

from ortools.sat.python import cp_model


def ensure_total_hours(rule, horizon_ub: int) -> Callable[[int], cp_model.IntVar]:
    """Return accessor that reuses per-employee total-hour IntVars."""

    cache: dict[int, cp_model.IntVar] | None = getattr(
        rule.model, "_total_hours_cache", None
    )
    if cache is None:
        cache = {}
        rule.model._total_hours_cache = cache

    def _getter(e: int) -> cp_model.IntVar:
        if e not in cache:
            total = rule.model.m.NewIntVar(0, horizon_ub, f"total_hours_e{e}")
            rule.model.m.Add(
                total
                == sum(
                    rule.model.x[(e, d, h)]
                    for d in range(rule.model.cfg.DAYS)
                    for h in range(rule.model.cfg.HOURS)
                )
            )
            cache[e] = total
        return cache[e]

    return _getter
