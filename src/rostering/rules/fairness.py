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

    def contribute_objective(self):
        if not self.enabled:
            return []

        C, M = self.model.cfg, self.model.m
        if C.N <= 0:
            return []

        # Equal-share target (same as before)
        total_required_lb = _required_hours_lower_bound(C)
        target = total_required_lb / C.N  # may be fractional
        t_floor, t_ceil = int(np.floor(target)), int(np.ceil(target))

        # Per-employee feasible upper bound for total hours
        horizon_ub = int(C.DAYS * C.HOURS)
        if getattr(C, "WEEKLY_MAX_HOURS", None) is not None:
            horizon_ub = min(horizon_ub, int(C.WEEKLY_MAX_HOURS))

        # ---- NEW: tiering parameters (all optional in Config) ----
        # How many hours of deviation to explicitly tier (controls model size).
        DEV_CAP = int(getattr(C, "FAIRNESS_DEV_CAP", min(horizon_ub, 40)))
        # Base weight for the original L1 term (your existing knob).
        W_BASE = int(getattr(C, "FAIRNESS_WEIGHT_PER_HOUR", 1))
        # Linear growth per hour of deviation (extra weight per hour beyond the base L1).
        W_TIER = int(getattr(C, "FAIRNESS_TIER_WEIGHT", W_BASE))

        # If you ever want exponential tiers instead, you can switch to:
        # BASE = float(getattr(C, "FAIRNESS_TIER_BASE", 1.2))
        # SCALE = int(getattr(C, "FAIRNESS_TIER_SCALE_INT", 100))
        # tier_weights = [int(round(SCALE * (BASE ** k))) for k in range(1, DEV_CAP + 1)]
        # For now we use linear tiers:
        tier_weights = [W_TIER * k for k in range(1, DEV_CAP + 1)]

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

            # Absolute deviation |T_e - target| linearized around fractional target
            dev = M.NewIntVar(0, horizon_ub, f"dev_e{e}")
            M.Add(dev >= T_e - t_floor)
            M.Add(dev >= t_ceil - T_e)

            # Keep your base L1 fairness penalty
            terms.append(W_BASE * dev)

            # ---- NEW: tiered, increasing penalty that hits outliers harder ----
            # b_{e,k} = 1  iff  dev >= k,   for k = 1..DEV_CAP
            # Adds a convex piecewise-linear penalty without quadratics.
            for k, w_k in enumerate(tier_weights, start=1):
                b = M.NewBoolVar(f"dev_ge_{k}_e{e}")
                M.Add(dev >= k).OnlyEnforceIf(b)
                M.Add(dev <= k - 1).OnlyEnforceIf(b.Not())
                terms.append(int(w_k) * b)

        return terms
