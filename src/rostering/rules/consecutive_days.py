from __future__ import annotations

from rostering.rules.base import Rule


class ConsecutiveDaysRule(Rule):
    """
    Track consecutive days worked, enforce optional hard caps, and emit soft
    penalties when runs exceed a threshold.

    Settings (RuleSpec.settings):
      pref_free: int, number of consecutive days allowed before soft penalties kick in (default 5)
      base: float >= 1.0, growth factor for penalties (default 2.0)
      scaler: float >= 0, multiplier prior to exponentiation (default 1.0)

      penalty = scaler * (base ** (runlen - pref_free))
    """

    order = 75
    name = "ConsecutiveDays"

    def __init__(self, model, **settings):
        super().__init__(model, **settings)
        self.pref_free = int(self.setting("pref_free", 5))
        self.base = float(self.setting("base", 2.0))
        self.scaler = float(self.setting("scaler", 1.0))
        self.max_gap = max(1, int(self.setting("max_gap", 4)))
        if self.base < 1.0:
            raise ValueError("consecutive-days 'base' must be >= 1.0")
        if self.scaler < 0:
            raise ValueError("consecutive-days 'scaler' must be >= 0")

    # ----- shared run-length logic -----
    def declare_vars(self) -> None:
        C, m = self.model.cfg, self.model.m
        self.model.consec_days_worked = {
            (e, d): m.NewIntVar(0, C.DAYS, f"run_e{e}_d{d}")
            for e in range(C.N)
            for d in range(C.DAYS)
        }

    def add_hard(self) -> None:
        C, data, m = self.model.cfg, self.model.data, self.model.m
        runlen = getattr(self.model, "consec_days_worked", None)
        if not runlen:
            return

        for e in range(C.N):
            # Base case for day 0.
            ct = m.Add(runlen[(e, 0)] == self.model.z[(e, 0)])
            self._guard(ct, f"RUNLEN-BASE[e={e}]")

            for d in range(1, C.DAYS):
                prev = runlen[(e, d - 1)]
                cur = runlen[(e, d)]

                ct = m.Add(cur <= prev + 1)
                self._guard(ct, f"RUNLEN-UP[e={e},d={d}]")

                ct = m.Add(cur <= C.DAYS * self.model.z[(e, d)])
                self._guard(ct, f"RUNLEN-Z[e={e},d={d}]")

                ct = m.Add(cur >= prev + 1 - C.DAYS * (1 - self.model.z[(e, d)]))
                self._guard(ct, f"RUNLEN-DOWN[e={e},d={d}]")

            # Hard max consecutive-day enforcement per staff member.
            if e < len(data.staff):
                limit = getattr(data.staff[e], "max_consec_days", None)
            else:
                limit = None

            if limit is None:
                continue

            try:
                limit_val = int(limit)
            except (TypeError, ValueError):
                continue

            if limit_val <= 0:
                continue

            for d in range(C.DAYS):
                ct = m.Add(runlen[(e, d)] <= limit_val)
                self._guard(ct, f"MAX-CONSEC[e={e},d={d},limit={limit_val}]")

    def contribute_objective(self):
        runlen = getattr(self.model, "consec_days_worked", None)
        if not runlen or self.scaler <= 0:
            return []

        C, m = self.model.cfg, self.model.m
        staff = list(getattr(self.model.data, "staff", []) or [])
        max_gap = min(self.max_gap, C.DAYS)
        penalty_table = [0]
        cumulative = 0
        for k in range(1, max_gap + 1):
            cumulative += int(round(self.scaler * (self.base**k)))
            penalty_table.append(cumulative)
        max_penalty = penalty_table[-1]

        cap_const = m.NewIntVar(max_gap, max_gap, "consec_cap_const")

        terms = []
        for e in range(C.N):
            limit_val = None
            if e < len(staff):
                limit = getattr(staff[e], "max_consec_days", None)
                if limit is not None:
                    try:
                        limit_val = int(limit)
                    except (TypeError, ValueError):
                        limit_val = None
            if limit_val is not None and self.pref_free >= limit_val:
                continue

            for d in range(C.DAYS):
                remaining_days = C.DAYS - d
                if remaining_days <= self.pref_free:
                    continue
                capped_run = m.NewIntVar(0, max_gap, f"consec_cap_e{e}_d{d}")
                m.AddMinEquality(capped_run, [runlen[(e, d)], cap_const])

                excess = m.NewIntVar(0, max_gap, f"consec_excess_e{e}_d{d}")
                over = m.NewBoolVar(f"consec_over_e{e}_d{d}")
                m.Add(capped_run >= self.pref_free + 1).OnlyEnforceIf(over)
                m.Add(capped_run <= self.pref_free).OnlyEnforceIf(over.Not())
                m.Add(excess == capped_run - self.pref_free).OnlyEnforceIf(over)
                m.Add(excess == 0).OnlyEnforceIf(over.Not())

                penalty = m.NewIntVar(0, max_penalty, f"consec_penalty_e{e}_d{d}")
                m.AddElement(excess, penalty_table, penalty)
                terms.append(penalty)
        return terms
