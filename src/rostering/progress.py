from ortools.sat.python import cp_model


class MinimalProgress(cp_model.CpSolverSolutionCallback):
    """
    A progress checking callback that logs statistics about discovered solutions.
    """

    def __init__(self, time_limit_sec: float, log_every_sec: float = 5.0):
        super().__init__()
        self.time_limit = (
            float(time_limit_sec) if time_limit_sec and time_limit_sec > 0 else None
        )
        self.log_every = float(log_every_sec)
        self.last_time = -1.0
        self.sols = 0
        self._best_field_width = 0
        self._ratio_field_width = 0
        self._printed_optimal_once = False
        self.history: list[tuple[float, float, float]] = []

        self.has_performed_initial_print = False

    def OnSolutionCallback(self):
        if not self.has_performed_initial_print:
            print_msg = (
                "\nbest: objective value (sum of penalties) of best solution found so far\n"
                "optimal: estimate of lowest possible objective value\n"
                "ratio: best / optimal (shows how far current best is from solver bound)\n\n"
            )
            print(print_msg)
            self.has_performed_initial_print = True
        self.sols += 1
        now = self.WallTime()
        best = self.ObjectiveValue()
        bound = self.BestObjectiveBound()
        self.history.append((now, best, bound))

        if self.last_time < 0 or (now - self.last_time) >= self.log_every:
            if not self._printed_optimal_once:
                print(f"Solver optimal lower bound: {bound:,.0f}")
                self._printed_optimal_once = True

            best_str = f"{best:,.0f}"
            self._best_field_width = max(self._best_field_width, len(best_str))
            best_field = best_str.ljust(self._best_field_width)

            if abs(bound) > 1e-9:
                ratio_val = abs(best) / max(1e-9, abs(bound))
                ratio_str = f"{ratio_val:,.2f}"
            else:
                ratio_str = "n/a"
            self._ratio_field_width = max(self._ratio_field_width, len(ratio_str))
            ratio_field = ratio_str.ljust(self._ratio_field_width)

            if self.time_limit:
                pct_val = min(100.0, 100.0 * now / self.time_limit)
                pct_field = f"{pct_val:6.2f}%"
            else:
                pct_field = "  n/a "
            print(
                f"[{now:5.1f}s] pct of time limit={pct_field} | best={best_field} | ratio={ratio_field} | sols={self.sols:<5.0f}",
                flush=True,
            )
            self.last_time = now

    def solution_history(self) -> list[tuple[float, float, float]]:
        """Return collected (wall_time, best_obj, best_bound) tuples."""
        return list(self.history)
