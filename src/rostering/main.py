from rostering.config import cfg
from rostering.data import build_input
from rostering.model import RosterModel
from rostering.progress import MinimalProgress
from rostering.reporting import Reporter


def main():
    cfg.validate()

    data = build_input(cfg, DAYS=cfg.DAYS, N=cfg.N, seed=7)
    model = RosterModel(cfg, data)

    reporter = Reporter(cfg)
    reporter.pre_solve(model)  # <-- before build/solve

    model.build()
    progress = MinimalProgress(cfg.TIME_LIMIT_SEC, cfg.LOG_EVERY_SEC)
    res = model.solve(progress_cb=progress)

    reporter.post_solve(res, data)  # <-- after solve


if __name__ == "__main__":
    main()
