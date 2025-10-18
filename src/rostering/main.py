from rostering.config import Config
from rostering.data import build_input
from rostering.model import RosterModel
from rostering.progress import MinimalProgress
from rostering.reporting import (
    print_per_employee_cap,
    print_precheck,
    print_shift_aware,
    print_summary,
    print_unsat_core,
)


def main():
    cfg = Config()
    cfg.validate()

    data = build_input(cfg, DAYS=cfg.DAYS, N=cfg.N, seed=7)

    model = RosterModel(cfg, data)
    cap, dem, ok_cap, buckets = model.precheck()
    print_precheck(cfg, cap, dem, ok_cap, buckets)

    model.build()
    progress = MinimalProgress(cfg.TIME_LIMIT_SEC, cfg.LOG_EVERY_SEC)
    res = model.solve(progress_cb=progress)

    print("Solver status:", res.status_name)
    if res.status_name == "INFEASIBLE":
        print_unsat_core(res.unsat_core_groups)
        return
    if res.objective_value is None:
        print("No trusted solution; exiting.")
        return

    print_summary(cfg, res)
    print_per_employee_cap(cfg, res.df_emp)
    print_shift_aware(cfg, res, data.staff, cfg.INSPECT_EMPLOYEE_IDS)


if __name__ == "__main__":
    main()
