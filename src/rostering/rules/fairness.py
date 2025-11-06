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
      DAYS, HOURS, N
      WEEKLY_MAX_HOURS (optional upper bound per-employee)
      FAIRNESS_WEIGHT_PER_HOUR (int)  -> base L1 weight
      SKILL_MIN (to derive the required-hours lower bound)

      # Exponential tiering controls:
      FAIRNESS_DEV_CAP (int, max deviation tiers to model, default=min(horizon_ub, 40))
      FAIRNESS_TIER_BASE (float, >1.0, growth base, default=1.2)
      FAIRNESS_TIER_SCALE_INT (int, positive, scale factor for integer weights, default=100)
    """

    order = 90
    name = "Fairness"

    def __init__(self, model):
        super().__init__(model)

    def contribute_objective(self):
        """
        Contribute to the model's objective function:
        - if not `self.enabled`, returns an empty list
        - if `C.N <= 0`, returns an empty list
        - otherwise, returns linear terms that encourage equal total hours
          across all employees, with an *exponentially increasing* penalty
          for larger deviations from the equal-share target.
        """
        if not self.enabled:
            return []

        C, M = self.model.cfg, self.model.m
        if C.N <= 0:
            return []

        # Equal-share target
        total_required_lb = _required_hours_lower_bound(C)
        target = total_required_lb / C.N  # may be fractional
        t_floor, t_ceil = int(np.floor(target)), int(np.ceil(target))

        # Per-employee feasible upper bound for total hours
        horizon_ub = int(C.DAYS * C.HOURS)
        if getattr(C, "WEEKLY_MAX_HOURS", None) is not None:
            horizon_ub = min(horizon_ub, int(C.WEEKLY_MAX_HOURS))

        # ---- Exponential tiering parameters ----

        # Do not penalise additionally if deviation is larger than this
        DEV_CAP = int(getattr(C, "FAIRNESS_MAX_DEVIATION_HOURS", min(horizon_ub, 40)))

        BASE = float(getattr(C, "FAIRNESS_BASE", 1.2))  # > 1.0
        SCALE = int(getattr(C, "FAIRNESS_SCALE", 1))  # positive numver

        print(
            f"Fairness: Base={BASE}, Scale={SCALE}, Max Dev={DEV_CAP}\n"
            f"Fairness penalty formula: Scale * ( Base ** Hours)\n"
            f"Max fairness penalty: Scale * (Base ** Max Dev) = {SCALE} * ({BASE} ** {DEV_CAP}) == {SCALE * (BASE**DEV_CAP):,.3f}"
        )

        assert (
            BASE > 1.0
        ), "FAIRNESS_BASE must be > 1.0 to enable exponential growth of penalties"
        assert SCALE >= 0

        # Integer tier weights: w_k = round(SCALE * BASE^k), k = 1..DEV_CAP
        tier_weights = [int(round(SCALE * (BASE**k))) for k in range(1, DEV_CAP + 1)]

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

            # Base L1 fairness penalty
            terms.append(dev)

            # ---- Exponential tiered penalty for outliers ----
            # b_{e,k} = 1  iff  dev >= k,   for k = 1..DEV_CAP
            for k, w_k in enumerate(tier_weights, start=1):
                b = M.NewBoolVar(f"dev_ge_{k}_e{e}")
                M.Add(dev >= k).OnlyEnforceIf(b)
                M.Add(dev <= k - 1).OnlyEnforceIf(b.Not())
                terms.append(int(w_k) * b)

        return terms
