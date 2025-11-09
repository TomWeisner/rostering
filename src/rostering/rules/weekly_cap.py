from rostering.rules.base import Rule
from rostering.rules.helpers import ensure_total_hours


class WeeklyCapRule(Rule):
    """
    Hard cap on total weekly hours per employee.

    Config used:
      WEEKLY_MAX_HOURS (int or None)
    """

    order = 70
    name = "WeeklyCap"

    def __init__(self, model, **settings):
        super().__init__(model, **settings)
        self.enabled = (
            model.cfg.WEEKLY_MAX_HOURS is not None
        )  # toggle by setting to None

    def add_hard(self):
        if not self.enabled:
            return
        C, M = self.model.cfg, self.model.m
        cap = int(C.WEEKLY_MAX_HOURS)
        get_total = ensure_total_hours(self, int(C.DAYS * C.HOURS))
        for e in range(C.N):
            total = get_total(e)
            ct = M.Add(total <= cap)
            self._guard(ct, f"WEEKLY-CAP[e={e}]")
