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
    solver.parameters.num_search_workers = cfg.NUM_PARALLEL_WORKERS
    solver.parameters.log_search_progress = False
    solver.parameters.log_to_stdout = True
    return solver


def _extract_unsat_groups(
    solver: cp_model.CpSolver, ctx: BuildContext
) -> dict[str, list[str]]:
    try:
        core = solver.SufficientAssumptionsForInfeasibility()
    except Exception:
        core = []
    if not core:
        return {}

    labels = ctx.core_labels(core)
    grouped = defaultdict(list)
    for lab in labels:
        key = lab.split("[", 1)[0]
        grouped[key].append(lab)
    return dict(grouped)


def solve_model(
    ctx: BuildContext, progress_cb=None
) -> Tuple[cp_model.CpSolver, str, dict[str, list[str]]]:
    """
    Run the solver. If infeasible and UNSAT core is enabled, return grouped core.
    Returns: (solver, status_name, unsat_core_groups)
    """

    def _solve(use_callback: bool) -> tuple[cp_model.CpSolver, int]:
        solver = setup_solver(ctx.cfg)
        status = (
            solver.SolveWithSolutionCallback(ctx.m, progress_cb)
            if use_callback and progress_cb is not None
            else solver.Solve(ctx.m)
        )
        return solver, status

    solver, status = _solve(use_callback=True)
    status_name = solver.StatusName(status)

    groups: dict[str, list[str]] = {}
    if status == cp_model.INFEASIBLE and ctx.cfg.ENABLE_UNSAT_CORE:
        groups = _extract_unsat_groups(solver, ctx)
        if not groups and progress_cb is not None:
            # Re-run without callback; CP-SAT only produces cores when no callback is used.
            solver, status = _solve(use_callback=False)
            status_name = solver.StatusName(status)
            if status == cp_model.INFEASIBLE:
                groups = _extract_unsat_groups(solver, ctx)

    return solver, status_name, groups
