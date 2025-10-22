from rostering.rules.base import Rule


class WeeklyCapRule(Rule):
    """
    Hard cap on total weekly hours per employee.

    Config used:
      WEEKLY_MAX_HOURS (int or None)
    """

    order = 70
    name = "WeeklyCap"

    def __init__(self, model):
        super().__init__(model)
        self.enabled = (
            model.cfg.WEEKLY_MAX_HOURS is not None
        )  # toggle by setting to None

    def add_hard(self):
        if not self.enabled:
            return
        C, M = self.model.cfg, self.model.m
        cap = int(C.WEEKLY_MAX_HOURS)
        for e in range(C.N):
            M.Add(
                sum(
                    self.model.x[(e, d, h)]
                    for d in range(C.DAYS)
                    for h in range(C.HOURS)
                )
                <= cap
            )
