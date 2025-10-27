from rostering.rules.base import Rule


class AvailabilityRule(Rule):
    """Define staff availability (all except holidays)"""

    order = 20
    name = "Availability"

    def add_hard(self):
        C, D, m = self.model.cfg, self.model.data, self.model.m
        for e in range(C.N):
            s = D.staff[e]
            forb_days = set(s.holidays)
            mask = D.allowed[e]
            for d in range(C.DAYS):
                for h in range(C.HOURS):
                    if (d in forb_days) or (not mask[h]):
                        m.Add(self.model.x[(e, d, h)] == 0)
