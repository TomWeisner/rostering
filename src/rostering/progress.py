from ortools.sat.python import cp_model


class MinimalProgress(cp_model.CpSolverSolutionCallback):
    def __init__(self, time_limit_sec: float, log_every_sec: float = 5.0):
        super().__init__()
        self.time_limit = (
            float(time_limit_sec) if time_limit_sec and time_limit_sec > 0 else None
        )
        self.log_every = float(log_every_sec)
        self.last_time = -1.0
        self.sols = 0

        self.has_performed_initial_print = False

    def OnSolutionCallback(self):
        if not self.has_performed_initial_print:
            print_msg = (
                "\nbest: objective value (sum of penalties) of best solution found so far\n"
                "optimal: estimate of lowest possible objective value\n"
                "gap: (optimal-best)/best\n\n"
            )
            print(print_msg)
            self.has_performed_initial_print = True
        self.sols += 1
        now = self.WallTime()
        if self.last_time < 0 or (now - self.last_time) >= self.log_every:
            best = self.ObjectiveValue()
            bound = self.BestObjectiveBound()
            denom = abs(best) if abs(best) > 1e-9 else 1.0
            gap = max(0.0, (best - bound) / denom * 100.0)
            pct = (
                f"{min(100.0, 100.0 * now / self.time_limit):.1f}%"
                if self.time_limit
                else ""
            )
            print(
                f"[{now:6.1f}s] sols={self.sols} | best={best:,.0f} | optimal={bound:,.0f} | gap={gap:.1f}% | {pct} of time limit",
                flush=True,
            )
            self.last_time = now
