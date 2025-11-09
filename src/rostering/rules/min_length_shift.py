from rostering.rules.base import Rule


class MinShiftLengthRule(Rule):
    """Ensure every scheduled shift covers at least MIN_SHIFT_HOURS of real work.

    Note: we do not need a symmetric “max shift” rule because the shift-length
    interval variable L[e,d] is already bounded above by MAX_SHIFT_HOURS when it
    is declared in VariablesRule. CP-SAT enforces that bound automatically, so
    only the *minimum* side requires an explicit constraint tying the realized
    hours to the declared length.
    """

    order = 40
    name = "MinRealizedLength"

    def add_hard(self):
        """Enforce min-length constraint by summing realized hour literals."""
        C, m = self.model.cfg, self.model.m
        for e in range(C.N):
            for d in range(C.DAYS):
                # w_cur_list captures hours assigned in the current day; spill_from_day
                # contains spillover hours that originated the previous day. Together
                # they represent every hour counted toward day d.
                parts = []
                parts += self.model.w_cur_list.get((e, d), [])
                parts += self.model.spill_from_day.get((e, d), [])

                if parts:
                    # lhs is the number of realized hour literals that fire.
                    lhs = sum(parts)
                    # rhs is MIN_SHIFT_HOURS * y[e,d]; if the day is scheduled (y=1)
                    # we require lhs >= rhs, otherwise rhs=0 and constraint is lax.
                    rhs = C.MIN_SHIFT_HOURS * self.model.y[(e, d)]
                    ct = m.Add(lhs >= rhs)
                    self._guard(ct, f"MINLEN[e={e},d={d}]")
                else:
                    # If there are no realized hours for this day, force y[e,d] = 0.
                    ct = m.Add(self.model.y[(e, d)] == 0)
                    self._guard(ct, f"MINLEN-ZERO[e={e},d={d}]")
