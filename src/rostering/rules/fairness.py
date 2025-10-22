import numpy as np

from rostering.rules.base import Rule


def _required_hours_lower_bound(C) -> int:
    """
    Skill-agnostic lower bound on total person-hours implied by SKILL_MIN:
    for each (d,h), take the largest single-skill minimum in that slot.
    If SKILL_MIN is None/empty, returns 0.
    """
    if getattr(C, "SKILL_MIN", None) is None:
        return 0
    total = 0
    for d in range(int(getattr(C, "DAYS", 0))):
        for h in range(int(getattr(C, "HOURS", 0))):
            slot_min = dict(C.SKILL_MIN[d][h])
            total += int(max(slot_min.values())) if slot_min else 0
    return total


class FairnessRule(Rule):
    """
    Soft-penalty for fairness: minimize L1 deviation from equal total hours.

    Config used:
      ENABLE_FAIRNESS (bool)
      DAYS, HOURS, N
      WEEKLY_MAX_HOURS (optional upper bound per-employee)
      FAIRNESS_WEIGHT_PER_HOUR (int)
      SKILL_MIN (to derive the required-hours lower bound)
    """

    order = 90
    name = "Fairness"

    def __init__(self, model):
        super().__init__(model)
        self.enabled = bool(model.cfg.ENABLE_FAIRNESS)

    def contribute_objective(self):
        if not self.enabled:
            return []

        C, M = self.model.cfg, self.model.m
        if C.N <= 0:
            return []

        # Equal-share target = lower bound of total required hours / headcount
        total_required_lb = _required_hours_lower_bound(C)
        target = total_required_lb / C.N  # may be fractional
        t_floor, t_ceil = int(np.floor(target)), int(np.ceil(target))

        # Per-employee feasible upper bound for total hours
        horizon_ub = int(C.DAYS * C.HOURS)
        if getattr(C, "WEEKLY_MAX_HOURS", None) is not None:
            horizon_ub = min(horizon_ub, int(C.WEEKLY_MAX_HOURS))

        terms = []
        for e in range(C.N):
            # Total hours assigned to employee e
            T_e = M.NewIntVar(0, horizon_ub, f"T_e{e}")
            M.Add(
                T_e
                == sum(
                    self.model.x[(e, d, h)]
                    for d in range(C.DAYS)
                    for h in range(C.HOURS)
                )
            )

            # L1 deviation |T_e - target| linearized with two half-planes
            dev = M.NewIntVar(0, horizon_ub, f"dev_e{e}")
            M.Add(dev >= T_e - t_floor)
            M.Add(dev >= t_ceil - T_e)

            terms.append(int(C.FAIRNESS_WEIGHT_PER_HOUR) * dev)

        return terms
