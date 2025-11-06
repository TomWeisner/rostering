from rostering.rules.base import Rule


class RunPenaltyRule(Rule):
    order = 80
    name = "RunPenalty"

    def declare_vars(self):
        C, m = self.model.cfg, self.model.m
        self.model.runlen = {
            (e, d): m.NewIntVar(0, C.DAYS, f"run_e{e}_d{d}")
            for e in range(C.N)
            for d in range(C.DAYS)
        }

    def add_hard(self):
        C, m = self.model.cfg, self.model.m
        for e in range(C.N):
            ct = m.Add(self.model.runlen[(e, 0)] == self.model.z[(e, 0)])
            self._guard(ct, f"RUNLEN-BASE[e={e}]")
            for d in range(1, C.DAYS):
                expr_prev = self.model.runlen[(e, d - 1)]
                expr_cur = self.model.runlen[(e, d)]

                ct = m.Add(expr_cur <= expr_prev + 1)
                self._guard(ct, f"RUNLEN-UP[e={e},d={d}]")

                ct = m.Add(expr_cur <= C.DAYS * self.model.z[(e, d)])
                self._guard(ct, f"RUNLEN-Z[e={e},d={d}]")

                ct = m.Add(
                    expr_cur >= expr_prev + 1 - C.DAYS * (1 - self.model.z[(e, d)])
                )
                self._guard(ct, f"RUNLEN-DOWN[e={e},d={d}]")

    def contribute_objective(self):
        C, m = self.model.cfg, self.model.m
        terms = []
        for e in range(C.N):
            for d in range(C.DAYS):
                for k in range(C.RUN_PEN_PREF_FREE + 1, C.DAYS + 1):
                    b = m.NewBoolVar(f"run_ge_{k}_e{e}_d{d}")
                    m.Add(self.model.runlen[(e, d)] >= k).OnlyEnforceIf(b)
                    m.Add(self.model.runlen[(e, d)] <= k - 1).OnlyEnforceIf(b.Not())
                    weight = C.RUN_PEN_SCALER * (
                        C.RUN_PEN_BASE ** (k - C.RUN_PEN_PREF_FREE)
                    )
                    terms.append(int(round(C.RUN_PEN_SCALE_INT * weight)) * b)
        return terms
