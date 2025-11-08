from datetime import date

from rostering.rules.base import Rule


class AvailabilityRule(Rule):
    """Define staff availability (all except holidays)"""

    order = 20
    name = "Availability"

    def add_hard(self):
        C, D, m = self.model.cfg, self.model.data, self.model.m
        base_date = C.START_DATE.date()
        for e in range(C.N):
            s = D.staff[e]
            forb_days = _dates_to_day_indices(s.holidays, base_date)
            mask = D.allowed[e]
            for d in range(C.DAYS):
                for h in range(C.HOURS):
                    if (d in forb_days) or (not mask[h]):
                        ct = m.Add(self.model.x[(e, d, h)] == 0)
                        self._guard(ct, f"AVAIL[e={e},d={d},h={h}]")


def _dates_to_day_indices(days: set[date], base_date: date) -> set[int]:
    indices: set[int] = set()
    for day in days:
        if isinstance(day, int):
            indices.add(day)
        elif isinstance(day, date):
            indices.add(int((day - base_date).days))
        else:
            raise TypeError(
                "Holiday entries must be int day indices or datetime.date objects."
            )
    return indices
