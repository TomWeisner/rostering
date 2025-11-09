import numpy as np

from rostering.rules.base import Rule
from rostering.rules.helpers import ensure_total_hours


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
    Penalise deviations from equal-share hours, with optional extra weight for higher bands.

    Fairness settings (RuleSpec):
      • base (>1.0):
          exponential growth factor. Example: base=1.3 means the 1st, 2nd, 3rd hours
          away from the target add 1.3¹≈1.3, 1.3²≈1.69, 1.3³≈2.20 penalty units in
          addition to penalties from earlier hours.
      • scale (>=0):
          linear multiplier applied to every tier. Example: base=1.3, scale=0.4,
          deviation=3h ⇒ 0.4*(1.3¹ + 1.3² + 1.3³) ≈ 2.24.
      • max_deviation_hours (int):
          clamps the AddElement lookup. Example: max_deviation_hours=6 limits the
          cumulative term to Σ_{k=1..6} scale * baseᵏ; hour 7+ reuses the hour-6 cost.

    Band shortfall settings (optional):
      • band_shortfall_base / band_shortfall_scale / band_shortfall_max_gap:
          shape the extra penalty curve for higher-band employees who fall short of
          the fleet average. Encodes the idea that higher-band employees should
          work at least as much as less paid colleagues.
          Example: base=1.25, scale=0.5, max_gap=4 means being
          3h short contributes 0.5*(1.25¹+1.25²+1.25³) ≈ 2.34.
      • band_shortfall_threshold:
          first band level that should be penalised (inclusive). Example
          threshold=1 penalises bands ≥1; threshold=3 penalises bands ≥3.
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
        staff = list(getattr(self.model.data, "staff", []) or [])
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

        get_total = ensure_total_hours(self, horizon_ub)
        total_sum = getattr(self.model, "_total_hours_sum", None)
        if total_sum is None:
            total_sum = M.NewIntVar(0, horizon_ub * C.N, "total_hours_sum")
            M.Add(total_sum == sum(get_total(e) for e in range(C.N)))
            self.model._total_hours_sum = total_sum

        # Optional 'band shortfall' extension. When enabled it layers an extra penalty
        # on top of fairness for higher bands who fall short of the fleet average.
        band_base = float(self.setting("band_shortfall_base", 1.25))
        band_scale = float(self.setting("band_shortfall_scale", 0.5))
        band_max_gap = int(self.setting("band_shortfall_max_gap", 4))
        band_threshold = int(self.setting("band_shortfall_threshold", 1))
        band_enabled = band_scale > 0 and band_base > 1.0 and band_max_gap > 0
        if band_enabled:
            band_table = [0]
            cumulative = 0
            for k in range(1, band_max_gap + 1):
                cumulative += int(round(band_scale * (band_base**k)))
                band_table.append(cumulative)
            band_cap_const = M.NewIntVar(
                band_max_gap, band_max_gap, "band_short_cap_const"
            )

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
            T_e = get_total(e)

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

            if band_enabled:
                # Translate band level into a multiplier exponent. Only bands above
                # the threshold receive the extra penalty.
                band_level = (
                    getattr(staff[e], "band", 1) if e < len(staff) else 1
                ) or 1
                if band_level >= band_threshold:
                    # shortfall captures how far this employee is below the fleet average.
                    shortfall = M.NewIntVar(0, horizon_ub, f"band_shortfall_e{e}")
                    gap_expr = total_sum - C.N * T_e
                    M.Add(C.N * shortfall >= gap_expr)
                    # Clamp the shortfall to the configured max gap.
                    capped_shortfall = M.NewIntVar(0, band_max_gap, f"band_cap_e{e}")
                    M.AddMinEquality(capped_shortfall, [shortfall, band_cap_const])
                    band_penalty = M.NewIntVar(0, band_table[-1], f"band_penalty_e{e}")
                    M.AddElement(capped_shortfall, band_table, band_penalty)
                    terms.append(band_penalty)

        return terms
