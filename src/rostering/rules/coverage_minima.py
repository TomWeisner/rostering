from rostering.rules.base import Rule


class CoverageAndMinimaRule(Rule):
    order = 60
    name = "CoverageMinima"

    def add_hard(self):
        C, D, m = self.model.cfg, self.model.data, self.model.m
        for d in range(C.DAYS):
            for h in range(C.HOURS):
                m.Add(sum(self.model.x[(e, d, h)] for e in range(C.N)) == C.COVER)
                m.Add(
                    sum(
                        self.model.x[(e, d, h)]
                        for e in range(C.N)
                        if D.staff[e].band >= 2
                    )
                    >= C.MIN_SENIOR
                )
                m.Add(
                    sum(
                        self.model.x[(e, d, h)] for e in range(C.N) if D.staff[e].skillA
                    )
                    >= C.MIN_SKILL_A
                )
                m.Add(
                    sum(
                        self.model.x[(e, d, h)] for e in range(C.N) if D.staff[e].skillB
                    )
                    >= C.MIN_SKILL_B
                )
                if C.ENABLE_UNSAT_CORE:
                    self.model.m.Add(
                        sum(self.model.x[(e, d, h)] for e in range(C.N)) == C.COVER
                    ).OnlyEnforceIf(
                        self.model.add_assumption(f"COVER[d={d},h={h:02d}]")
                    )
                    self.model.m.Add(
                        sum(
                            self.model.x[(e, d, h)]
                            for e in range(C.N)
                            if D.staff[e].band >= 2
                        )
                        >= C.MIN_SENIOR
                    ).OnlyEnforceIf(
                        self.model.add_assumption(f"MIN_SENIOR[d={d},h={h:02d}]")
                    )
                    self.model.m.Add(
                        sum(
                            self.model.x[(e, d, h)]
                            for e in range(C.N)
                            if D.staff[e].skillA
                        )
                        >= C.MIN_SKILL_A
                    ).OnlyEnforceIf(
                        self.model.add_assumption(f"MIN_A[d={d},h={h:02d}]")
                    )
                    self.model.m.Add(
                        sum(
                            self.model.x[(e, d, h)]
                            for e in range(C.N)
                            if D.staff[e].skillB
                        )
                        >= C.MIN_SKILL_B
                    ).OnlyEnforceIf(
                        self.model.add_assumption(f"MIN_B[d={d},h={h:02d}]")
                    )
