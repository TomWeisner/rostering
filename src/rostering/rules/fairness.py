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
    Balance total assigned hours across employees by penalising deviations from
    the "equal share" target.

    This class intentionally serves as a template for other rules:
      • It documents every tuning knob.
      • It explains each modelling phase in comments.
      • It demonstrates how to convert human language requirements into CP-SAT
        linear expressions with clear intermediate variables.

    Settings (RuleSpec):
      base: float (>1.0)
          Growth factor for the exponential tiers. Larger bases punish outliers
          more aggressively because each extra hour multiplies the cost.
      scale: float (>=0)
          Multiplier applied before rounding weights to integers. Use it to
          change the overall magnitude of fairness penalties relative to other
          soft objectives.
      max_deviation_hours: int
          Caps how many tiers we build. Once the deviation exceeds this value,
          additional hours do not create new penalty literals, which keeps the
          model small.

    Required config fields:
      cfg.DAYS, cfg.HOURS, cfg.N
      cfg.SKILL_MIN (to estimate the total demand)
      cfg.WEEKLY_MAX_HOURS (optional per-employee bound)
    """

    order = 90
    name = "Fairness"

    def __init__(self, model, **settings):
        super().__init__(model, **settings)

    def contribute_objective(self):
        # If the rule is disabled or the roster is empty, there is nothing to add.
        if not self.enabled:
            return []

        C, M = self.model.cfg, self.model.m
        if C.N <= 0:
            return []

        # ------------------------------------------------------------------
        # 1) Compute the equal-share target.
        #    We use the lower bound implied by SKILL_MIN to avoid the trivial
        #    "zero target" when no skills are required.
        # ------------------------------------------------------------------
        total_required_lb = _required_hours_lower_bound(C)
        target = total_required_lb / C.N  # may be fractional
        t_floor, t_ceil = int(np.floor(target)), int(np.ceil(target))

        # ------------------------------------------------------------------
        # 2) Derive a safe upper bound on each employee's workable hours.
        #    This keeps intermediate IntVars tight.
        # ------------------------------------------------------------------
        horizon_ub = int(C.DAYS * C.HOURS)
        if getattr(C, "WEEKLY_MAX_HOURS", None) is not None:
            horizon_ub = min(horizon_ub, int(C.WEEKLY_MAX_HOURS))

        # ------------------------------------------------------------------
        # 3) Exponential tier parameters pulled from settings.
        # ------------------------------------------------------------------
        DEV_CAP = int(self.setting("max_deviation_hours", min(horizon_ub, 8)))
        BASE = float(self.setting("base", 1.2))  # > 1.0
        SCALE = float(self.setting("scale", 1.0))  # positive number

        print(
            f"Fairness: Base={BASE}, Scale={SCALE}, Max Dev={DEV_CAP}\n"
            f"Fairness penalty formula: Scale * ( Base ** Hours)\n"
            f"Max fairness penalty: Scale * (Base ** Max Dev) = {SCALE} * ({BASE} ** {DEV_CAP}) == {SCALE * (BASE**DEV_CAP):,.3f}"
        )

        assert (
            BASE > 1.0
        ), "Fairness base must be > 1.0 to enable exponential growth of penalties"
        assert SCALE >= 0

        # Precompute cumulative penalty table so we can look up the total weight
        # with a single AddElement instead of spawning many Boolean tiers.
        penalty_table = [0]
        cumulative = 0
        for k in range(1, DEV_CAP + 1):
            cumulative += int(round(SCALE * (BASE**k)))
            penalty_table.append(cumulative)
        max_penalty = penalty_table[-1]

        terms = []

        cap_constant = M.NewIntVar(DEV_CAP, DEV_CAP, "fair_dev_cap_const")

        for e in range(C.N):
            # ------------------------------------------------------------------
            # 4) Total hours for employee e.
            #    Example: DAYS=5, HOURS=24 -> horizon_ub=120 so T_e ∈ [0,120].
            #    We enforce
            #        T_e = Σ_{d=0..D-1} Σ_{h=0..H-1} x[e,d,h]
            #    meaning the total stored in T_e must exactly match the worked
            #    hours. Without this equality, the solver could set T_e=0 even
            #    when the employee covers 60 hours, effectively dodging fairness
            #    penalties altogether.
            # ------------------------------------------------------------------
            T_e = M.NewIntVar(0, horizon_ub, f"T_e{e}")
            M.Add(
                T_e
                == sum(
                    self.model.x[(e, d, h)]
                    for d in range(C.DAYS)
                    for h in range(C.HOURS)
                )
            )

            # ------------------------------------------------------------------
            # 5) Linearise |T_e - target| by bounding it between floor/ceil.
            #    Example target = 37.5h -> t_floor=37, t_ceil=38.
            #      • If T_e = 45, dev must be ≥ 45 - 37 = 8 (over-scheduled).
            #      • If T_e = 30, dev must be ≥ 38 - 30 = 8 (under-scheduled).
            #    With both inequalities active, dev mirrors |T_e - 37.5| while
            #    keeping everything in integer arithmetic (CP-SAT cannot use
            #    floating-point constants directly in constraints).
            # ------------------------------------------------------------------
            dev = M.NewIntVar(0, horizon_ub, f"dev_e{e}")
            M.Add(dev >= T_e - t_floor)
            M.Add(dev >= t_ceil - T_e)

            terms.append(dev)

            # ------------------------------------------------------------------
            # 6) Exponential tiers via lookup table.
            #    Example: base=1.4, scale=1.0, max_dev=8.
            #      • penalty_table[1] ≈ 1.4
            #      • penalty_table[4] ≈ 1.4 + 2.0 + 2.7 + 3.8 ≈ 9.9
            #    Instead of four BoolVars, we clamp dev to 8 and feed it
            #    directly into AddElement, which returns the cumulative weight.
            # ------------------------------------------------------------------
            capped_dev = M.NewIntVar(0, DEV_CAP, f"dev_cap_e{e}")
            M.AddMinEquality(capped_dev, [dev, cap_constant])

            penalty = M.NewIntVar(0, max_penalty, f"fair_penalty_e{e}")
            M.AddElement(capped_dev, penalty_table, penalty)
            terms.append(penalty)

        return terms
