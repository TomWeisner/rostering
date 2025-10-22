from ortools.sat.python import cp_model

from rostering.rules.base import Rule


class IntervalLinkRule(Rule):
    order = 30
    name = "IntervalLink"

    def __init__(self, model):
        super().__init__(model)

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

    def add_hard(self):
        C, D, m = self.model.cfg, self.model.data, self.model.m

        for e in range(C.N):
            mask = D.allowed[e]
            forb_days = set(D.staff[e].holidays)
            for d in range(C.DAYS):
                for h in range(C.HOURS):
                    # S<=h and h<S+L
                    b1 = m.NewBoolVar(f"b1_e{e}_d{d}_h{h}")
                    m.Add(self.model.S[(e, d)] <= h).OnlyEnforceIf(b1)
                    m.Add(self.model.S[(e, d)] >= h + 1).OnlyEnforceIf(b1.Not())

                    b2 = m.NewBoolVar(f"b2_e{e}_d{d}_h{h}")
                    m.Add(
                        self.model.S[(e, d)] + self.model.L[(e, d)] >= h + 1
                    ).OnlyEnforceIf(b2)
                    m.Add(
                        self.model.S[(e, d)] + self.model.L[(e, d)] <= h
                    ).OnlyEnforceIf(b2.Not())

                    w_cur = m.NewBoolVar(f"wcur_e{e}_d{d}_h{h}")
                    m.Add(w_cur <= self.model.y[(e, d)])
                    m.Add(w_cur <= b1)
                    m.Add(w_cur <= b2)
                    m.Add(w_cur >= self.model.y[(e, d)] + b1 + b2 - 2)

                    if (not mask[h]) or (d in forb_days):
                        m.Add(w_cur == 0)
                    else:
                        self.model.w_cur_list[(e, d)].append(w_cur)

                    # spill from previous day
                    if d > 0:
                        bOver = m.NewBoolVar(
                            f"bOver_e{e}_d{d}_h{h}"
                        )  # S_prev + L_prev > 24
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)] >= 25
                        ).OnlyEnforceIf(bOver)
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)] <= 24
                        ).OnlyEnforceIf(bOver.Not())

                        bHcov = m.NewBoolVar(
                            f"bHcov_e{e}_d{d}_h{h}"
                        )  # h < S_prev + L_prev - 24
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)]
                            >= h + 25
                        ).OnlyEnforceIf(bHcov)
                        m.Add(
                            self.model.S[(e, d - 1)] + self.model.L[(e, d - 1)]
                            <= h + 24
                        ).OnlyEnforceIf(bHcov.Not())

                        w_prev = m.NewBoolVar(f"wprev_e{e}_d{d}_h{h}")
                        m.Add(w_prev <= self.model.y[(e, d - 1)])
                        m.Add(w_prev <= bOver)
                        m.Add(w_prev <= bHcov)
                        m.Add(w_prev >= self.model.y[(e, d - 1)] + bOver + bHcov - 2)

                        if (not mask[h]) or (d in forb_days):
                            m.Add(w_prev == 0)
                        else:
                            self.model.spill_from_day[(e, d - 1)].append(w_prev)
                    else:
                        w_prev = m.NewConstant(0)

                    # x = OR(w_cur, w_prev)
                    m.Add(self.model.x[(e, d, h)] >= w_cur)
                    if isinstance(w_prev, cp_model.IntVar):
                        m.Add(self.model.x[(e, d, h)] >= w_prev)
                        m.Add(self.model.x[(e, d, h)] <= w_cur + w_prev)
                    else:
                        m.Add(self.model.x[(e, d, h)] <= w_cur)

        # z: worked any hour
        for e in range(C.N):
            for d in range(C.DAYS):
                m.Add(
                    sum(self.model.x[(e, d, h)] for h in range(C.HOURS)) >= 1
                ).OnlyEnforceIf(self.model.z[(e, d)])
                m.Add(
                    sum(self.model.x[(e, d, h)] for h in range(C.HOURS)) == 0
                ).OnlyEnforceIf(self.model.z[(e, d)].Not())
