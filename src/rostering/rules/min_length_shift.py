from rostering.rules.base import Rule


class MinRealizedLengthRule(Rule):
    order = 40
    name = "MinRealizedLength"

    def add_hard(self):
        C, m = self.model.cfg, self.model.m
        # sum(allowed current + allowed spill) >= MIN_SHIFT_H * y
        for e in range(C.N):
            for d in range(C.DAYS):
                parts = []
                parts += self.model.w_cur_list.get((e, d), [])
                parts += self.model.spill_from_day.get((e, d), [])
                if parts:
                    m.Add(sum(parts) >= C.MIN_SHIFT_H * self.model.y[(e, d)])
                else:
                    m.Add(self.model.y[(e, d)] == 0)
