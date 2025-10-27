from rostering.rules.base import Rule


class VariablesRule(Rule):
    """Define decision variables"""

    order = 10
    name = "Variables"

    def declare_vars(self):
        C = self.model.cfg
        m = self.model.m
        # Intervals: one optional shift per employee/day
        self.model.y = {
            (e, d): m.NewBoolVar(f"y_e{e}_d{d}")
            for e in range(C.N)
            for d in range(C.DAYS)
        }
        self.model.S = {
            (e, d): m.NewIntVar(0, C.HOURS - 1, f"S_e{e}_d{d}")
            for e in range(C.N)
            for d in range(C.DAYS)
        }
        self.model.L = {
            (e, d): m.NewIntVar(C.MIN_SHIFT_H, C.MAX_SHIFT_H, f"L_e{e}_d{d}")
            for e in range(C.N)
            for d in range(C.DAYS)
        }
        # Hourly realized assignment
        self.model.x = {
            (e, d, h): m.NewBoolVar(f"x_e{e}_d{d}_h{h}")
            for e in range(C.N)
            for d in range(C.DAYS)
            for h in range(C.HOURS)
        }
        # Day on/off
        self.model.z = {
            (e, d): m.NewBoolVar(f"z_e{e}_d{d}")
            for e in range(C.N)
            for d in range(C.DAYS)
        }
