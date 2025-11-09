from __future__ import annotations

from rostering.rules.base import Rule


class BandShortfallPenaltyRule(Rule):
    """
    Penalise higher-band staff when they fall short of the average hours.

    Rationale
    ---------
    Higher-band employees are often more expensive or in short supply. If they
    end up working fewer hours than their peers, the business may not be getting
    the expected value from those roles. This rule compares each employee’s
    assigned hours to the fleet average and adds exponentially growing penalties
    for shortfalls, scaled by the staff member’s band.

    Settings (RuleSpec.settings):
      base: float (>1.0)
          Exponential growth factor for the shortfall. Larger bases mean the
          penalty escalates quickly for each missing hour.
      scale: float (>=0)
          Baseline multiplier applied before rounding to integers.
      band_base: float (>1.0)
          Additional exponential factor applied per band (band 3 > band 2).
      max_gap: int
          Maximum shortfall (in hours) we model. Larger gaps are clamped to
          this value, which keeps the lookup table small.

    Example
    -------
    Suppose base=1.3, scale=1.0, band_base=1.2, max_gap=8. For a band-3
    employee, missing 3 hours would incur roughly:
        penalty ≈ scale_int * 1.3^3 * 1.2^(3-2)
    which is significantly larger than the same shortfall for a band-1 employee.
    """

    order = 95
    name = "BandShortfallPenalty"

    def contribute_objective(self) -> list:
        if not self.enabled:
            return []

        cfg = self.model.cfg
        if cfg.N <= 1:  # Need more than one employee to compare averages
            return []

        staff = list(getattr(self.model.data, "staff", []) or [])
        if not staff:
            return []

        # Only bands above 1 receive penalties, so collect their indices once.
        applicable_indices: list[int] = []
        for idx in range(min(cfg.N, len(staff))):
            band = getattr(staff[idx], "band", 1) or 1
            if band > 1:
                applicable_indices.append(idx)

        if not applicable_indices:
            return []

        model = self.model.m
        # Maximum hours an employee could work over the planning horizon.
        horizon_ub = int(cfg.DAYS * cfg.HOURS)
        total_hours_ub = horizon_ub * cfg.N

        # Build per-employee total-hour IntVars. CP-SAT IntVars must be given an
        # explicit lower/upper bound; here we clamp to [0, horizon_ub]. The Add()
        # call is how we express “total == sum(x[e,d,h])”.
        employee_totals: list = []
        for e in range(cfg.N):
            total = model.NewIntVar(0, horizon_ub, f"band_short_hours_e{e}")
            model.Add(
                total
                == sum(
                    self.model.x[(e, d, h)]
                    for d in range(cfg.DAYS)
                    for h in range(cfg.HOURS)
                )
            )
            employee_totals.append(total)

        # Global sum of all hours. We only need this once, so we create a single
        # IntVar and constrain it to equal the sum of each employee’s hours.
        total_hours = model.NewIntVar(0, total_hours_ub, "band_short_total_hours")
        model.Add(total_hours == sum(employee_totals))

        # Pull exponential controls from the RuleSpec. base/scale govern the
        # generic shortfall curve; band_base adds extra weight per band level;
        # max_gap prevents the lookup table from growing without bound.
        base = float(self.setting("base", 1.3))
        scale = float(self.setting("scale", 1.0))
        band_base = float(self.setting("band_base", 1.25))
        max_gap_setting = int(self.setting("max_gap", 4))
        max_gap = min(max_gap_setting, horizon_ub)

        if scale <= 0 or base <= 1.0 or band_base <= 1.0 or max_gap <= 0:

            return []

        # Precompute cumulative penalty table for shortfall = 0..max_gap.
        # Each entry stores the cumulative exponential penalty so we can map
        # “shortfall hours” -> weight with a single AddElement later.
        penalty_table = [0]
        cumulative = 0
        for k in range(1, max_gap + 1):
            cumulative += int(round(scale * (base**k)))
            penalty_table.append(cumulative)

        # Fixed IntVar (value == max_gap) so we can clamp shortfall via
        # AddMinEquality without recomputing the max constant each time.
        cap_const = model.NewIntVar(max_gap, max_gap, "band_short_gap_cap_const")

        terms = []
        for idx in applicable_indices:
            band = getattr(staff[idx], "band", 1) or 1
            shortfall = model.NewIntVar(0, horizon_ub, f"band_short_gap_e{idx}")
            # We compare each employee against the average hours (total / N).
            # To keep the arithmetic integral we multiply both sides by cfg.N,
            # i.e. shortfall ≥ (total_hours - N * personal_hours) / N.
            gap_expr = total_hours - cfg.N * employee_totals[idx]
            model.Add(cfg.N * shortfall >= gap_expr)

            # Clamp the shortfall to max_gap so that excessive gaps fall into
            # the last bucket rather than creating new literals.
            capped_gap = model.NewIntVar(0, max_gap, f"band_short_cap_e{idx}")
            model.AddMinEquality(capped_gap, [shortfall, cap_const])

            # Higher-band employees get an extra multiplier (e.g., band 3
            # will cost more than band 2 for the same shortfall).
            band_multiplier = band_base ** (max(0, band - 2))
            # AddElement(index_var, table, target_var) is CP-SAT’s “lookup”.
            # We scale the table per band so higher bands incur higher costs.
            scaled_table = [int(round(val * band_multiplier)) for val in penalty_table]
            band_penalty = model.NewIntVar(
                0, max(scaled_table), f"band_short_penalty_e{idx}"
            )
            model.AddElement(capped_gap, scaled_table, band_penalty)
            terms.append(band_penalty)

        return terms
