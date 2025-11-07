from rostering.rules.base import Rule


class MinRealizedLengthRule(Rule):
    order = 40
    name = "MinRealizedLength"

    def add_hard(self):
        C, m = self.model.cfg, self.model.m
        # sum(allowed current + allowed spill) >= MIN_SHIFT_HOURS * y
        for e in range(C.N):
            for d in range(C.DAYS):
                parts = []
                parts += self.model.w_cur_list.get((e, d), [])
                parts += self.model.spill_from_day.get((e, d), [])
                if parts:
                    lhs = sum(parts)
                    rhs = C.MIN_SHIFT_HOURS * self.model.y[(e, d)]
                    ct = m.Add(lhs >= rhs)
                    self._guard(ct, f"MINLEN[e={e},d={d}]")
                else:
                    ct = m.Add(self.model.y[(e, d)] == 0)
                    self._guard(ct, f"MINLEN-ZERO[e={e},d={d}]")
