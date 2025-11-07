from __future__ import annotations

from rostering.rules.base import Rule


class ShiftIntervalRule(Rule):
    """
    Convert a chosen shift interval into hour-level “worked” flags (and a day-worked flag).

    Purpose
    -------
    Link the abstract shift decision (y[e,d], start S[e,d], length L[e,d]) to:
      • x[e,d,h]  = 1 iff hour h of day d is worked (either inside today's shift
                    or spilled over from yesterday’s late shift)
      • z[e,d]    = 1 iff any hour on day d is worked (∨_h x[e,d,h])

    Data (read-only)
    ----------------
    cfg.N        : number of employees
    cfg.DAYS     : planning horizon (days)
    cfg.HOURS    : hours per day (e.g., 24)
    data.allowed[e][h] : hour availability mask for employee e (True if allowed)
    data.staff[e].holidays : set of day indices e must not work

    Variables (provided by the model)
    ---------------------------------
    y[e,d]     : BoolVar, 1 if a shift is assigned on day d for employee e
    S[e,d]     : IntVar,   shift start hour (0..HOURS-1)
    L[e,d]     : IntVar,   shift length (>= 0)
    x[e,d,h]   : BoolVar,  1 if hour h of day d is worked (current day or spillover)
    z[e,d]     : BoolVar,  1 if any hour of day d is worked

    Helper literals created here
    ----------------------------
    w_cur[e,d,h]  : 1 if hour h is inside today's interval AND y[e,d]=1
    w_prev[e,d,h] : 1 if hour h is covered by yesterday’s shift spillover AND y[e,d-1]=1

    Convenience lists (for potential soft objectives elsewhere)
    -----------------------------------------------------------
    w_cur_list[(e,d)]       : list of w_cur literals that are legal (allowed & not holiday)
    spill_from_day[(e,d)]   : list of spillover literals that originate on day d
    """

    order = 30
    name = "ShiftIntervalCoverage"

    def __init__(self, model):
        super().__init__(model)

    # ------------------------------------------------------------------ #
    # Declare containers for helper literals we expose to other rules
    # ------------------------------------------------------------------ #
    def declare_vars(self):
        self.model.w_cur_list = {
            (e, d): []
            for e in range(self.model.cfg.N)
            for d in range(self.model.cfg.DAYS)
        }
        self.model.spill_from_day = {
            (e, d): []
            for e in range(self.model.cfg.N)
            for d in range(self.model.cfg.DAYS)
        }

    # ------------------------------------------------------------------ #
    # Hard constraints: build w_cur / w_prev, set x = OR(w_cur, w_prev),
    # and set z ⇔ any hour worked.
    # ------------------------------------------------------------------ #
    def add_hard(self):
        C, D, m = self.model.cfg, self.model.data, self.model.m

        for e in range(C.N):
            allowed_mask = D.allowed[e]
            forbidden_days = set(D.staff[e].holidays)

            for d in range(C.DAYS):
                for h in range(C.HOURS):
                    # ---------- Current-day coverage: w_cur = y AND (S <= h) AND (h < S+L) ----------
                    # b1 ↔ (S[e,d] ≤ h)
                    b1 = m.NewBoolVar(f"b1_e{e}_d{d}_h{h}")
                    m.Add(self.model.S[(e, d)] <= h).OnlyEnforceIf(b1)
                    m.Add(self.model.S[(e, d)] >= h + 1).OnlyEnforceIf(b1.Not())

                    # b2 ↔ (h < S[e,d] + L[e,d])  <=>  S+L ≥ h+1
                    b2 = m.NewBoolVar(f"b2_e{e}_d{d}_h{h}")
                    m.Add(
                        self.model.S[(e, d)] + self.model.L[(e, d)] >= h + 1
                    ).OnlyEnforceIf(b2)
                    m.Add(
                        self.model.S[(e, d)] + self.model.L[(e, d)] <= h
                    ).OnlyEnforceIf(b2.Not())

                    w_cur = m.NewBoolVar(f"wcur_e{e}_d{d}_h{h}")
                    # AND(y, b1, b2)
                    m.Add(w_cur <= self.model.y[(e, d)])
                    m.Add(w_cur <= b1)
                    m.Add(w_cur <= b2)
                    m.Add(w_cur >= self.model.y[(e, d)] + b1 + b2 - 2)

                    # Respect availability and holidays
                    if (not allowed_mask[h]) or (d in forbidden_days):
                        m.Add(w_cur == 0)
                    else:
                        self.model.w_cur_list[(e, d)].append(w_cur)

                    # ---------- Previous-day spillover: w_prev ----------
                    # Always create a BoolVar so we can unify constraints below.
                    w_prev = m.NewBoolVar(f"wprev_e{e}_d{d}_h{h}")
                    if d == 0:
                        # Day 0 has no previous day: fix to 0.
                        m.Add(w_prev == 0)
                    else:
                        # bOver ↔ (S[e,d-1] + L[e,d-1] > 24)  (encode as ≥25 since hours are integers)
                        bOver = m.NewBoolVar(f"bOver_e{e}_d{d}_h{h}")
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)] >= 25
                        ).OnlyEnforceIf(bOver)
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)] <= 24
                        ).OnlyEnforceIf(bOver.Not())

                        # bHcov ↔ (h < S[e,d-1] + L[e,d-1] - 24)  <=>  S+L ≥ h+25
                        bHcov = m.NewBoolVar(f"bHcov_e{e}_d{d}_h{h}")
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)]
                            >= h + 25
                        ).OnlyEnforceIf(bHcov)
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)]
                            <= h + 24
                        ).OnlyEnforceIf(bHcov.Not())

                        # AND(y_prev, bOver, bHcov)
                        m.Add(w_prev <= self.model.y[(e, d - 1)])
                        m.Add(w_prev <= bOver)
                        m.Add(w_prev <= bHcov)
                        m.Add(w_prev >= self.model.y[(e, d - 1)] + bOver + bHcov - 2)

                        if (not allowed_mask[h]) or (d in forbidden_days):
                            m.Add(w_prev == 0)
                        else:
                            # Track spillover literals by the day they originate from (d-1)
                            self.model.spill_from_day[(e, d - 1)].append(w_prev)

                    # ---------- Hour worked indicator: x = OR(w_cur, w_prev) ----------
                    # For Booleans, max equals OR.
                    m.AddMaxEquality(self.model.x[(e, d, h)], [w_cur, w_prev])

        # ---------- Day worked indicator: z[e,d] ⇔ any hour worked ----------
        for e in range(C.N):
            for d in range(C.DAYS):
                total = sum(self.model.x[(e, d, h)] for h in range(C.HOURS))
                # If z=1 then at least one hour must be worked.
                m.Add(total >= 1).OnlyEnforceIf(self.model.z[(e, d)])
                # If z=0 then no hour may be worked.
                m.Add(total == 0).OnlyEnforceIf(self.model.z[(e, d)].Not())
