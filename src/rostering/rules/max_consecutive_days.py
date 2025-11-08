from __future__ import annotations

from rostering.rules.base import Rule


class MaxConsecutiveDaysRule(Rule):
    """
    Enforce per-employee maximum consecutive working days using the run-length
    variables produced by RunPenaltyRule. When a staff member declares
    `max_consec_days`, every day in the horizon must respect that cap.
    """

    order = 75
    name = "MaxConsecutiveDays"

    def add_hard(self) -> None:
        runlen = getattr(self.model, "runlen", None)
        if not runlen:
            return

        C, data, m = self.model.cfg, self.model.data, self.model.m

        for e, staff in enumerate(data.staff):
            limit = getattr(staff, "max_consec_days", None)
            if limit is None:
                continue

            try:
                limit_val = int(limit)
            except (TypeError, ValueError):
                continue

            if limit_val <= 0:
                # Non-positive caps effectively prohibit work, but since other rules
                # already enforce feasibility, we skip enforcing nonsense limits.
                continue

            for d in range(C.DAYS):
                ct = m.Add(self.model.runlen[(e, d)] <= limit_val)
                self._guard(ct, f"MAX-CONSEC[e={e},d={d},limit={limit_val}]")
