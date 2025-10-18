# rostering/solver.py
from __future__ import annotations

from collections import defaultdict
from typing import Tuple

from ortools.sat.python import cp_model

from rostering.build import BuildContext
from rostering.config import Config


def setup_solver(cfg: Config) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.TIME_LIMIT_SEC
    solver.parameters.num_search_workers = cfg.NUM_WORKERS
    solver.parameters.log_search_progress = False
    solver.parameters.log_to_stdout = False
    return solver


def solve_model(
    ctx: BuildContext, progress_cb=None
) -> Tuple[cp_model.CpSolver, str, dict[str, list[str]]]:
    """
    Run the solver. If infeasible and UNSAT core is enabled, return grouped core.
    Returns: (solver, status_name, unsat_core_groups)
    """
    solver = setup_solver(ctx.cfg)
    status = (
        solver.SolveWithSolutionCallback(ctx.m, progress_cb)
        if progress_cb
        else solver.Solve(ctx.m)
    )
    status_name = solver.StatusName(status)

    groups: dict[str, list[str]] = {}
    if status == cp_model.INFEASIBLE and ctx.cfg.ENABLE_UNSAT_CORE:
        try:
            core = solver.SufficientAssumptionsForInfeasibility()
        except Exception:
            core = []
        if core:
            labels = ctx.core_labels(core)
            grouped = defaultdict(list)
            for lab in labels:
                key = lab.split("[", 1)[0]
                grouped[key].append(lab)
            groups = dict(grouped)
    return solver, status_name, groups
