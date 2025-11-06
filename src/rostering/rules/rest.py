from rostering.rules.base import Rule


class RestRule(Rule):
    """
    Minimum rest hours between the end of day d and start of day d+1
    for the SAME employee, when both days have a shift.

    Intervals:
      y[e,d] = 1 if day d has a shift
      S[e,d] = start hour (0..23)
      L[e,d] = length (MIN_SHIFT_HOURS..MAX_SHIFT_HOURS)

    Constraint:
      If y[e,d] = y[e,d+1] = 1 then
        S[e,d+1] >= REST_HOURS + S[e,d] + L[e,d] - 24

    Config used:
      REST_HOURS (int; 0 disables)
      ENABLE_UNSAT_CORE (bool; adds mirrored assumption-guarded copy)
    """

    order = 50
    name = "Rest"

    def __init__(self, model):
        super().__init__(model)
        self.enabled = model.cfg.REST_HOURS > 0  # disable with 0

    def add_hard(self):
        if not self.enabled:
            return
        C, M = self.model.cfg, self.model.m

        for e in range(C.N):
            for d in range(C.DAYS - 1):
                # Hard constraint active only if both days have shifts
                M.Add(
                    self.model.S[(e, d + 1)]
                    >= C.REST_HOURS + self.model.S[(e, d)] + self.model.L[(e, d)] - 24
                ).OnlyEnforceIf([self.model.y[(e, d)], self.model.y[(e, d + 1)]])

                # Mirrored copy for readable UNSAT core (optional)
                if C.ENABLE_UNSAT_CORE:
                    a = self.model.add_assumption(f"REST{C.REST_HOURS}[e={e},d={d}]")
                    M.Add(
                        self.model.S[(e, d + 1)]
                        >= C.REST_HOURS
                        + self.model.S[(e, d)]
                        + self.model.L[(e, d)]
                        - 24
                    ).OnlyEnforceIf([self.model.y[(e, d)], self.model.y[(e, d + 1)], a])
