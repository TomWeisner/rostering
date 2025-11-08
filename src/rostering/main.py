from __future__ import annotations

from typing import Callable

from ortools.sat.python import cp_model

from rostering.config import Config, cfg
from rostering.input_data import InputData, build_input
from rostering.model import RosterModel
from rostering.progress import MinimalProgress
from rostering.reporting import Reporter
from rostering.result_types import SolveResult

InputBuilder = Callable[[Config], InputData]


def default_input_builder(config: Config) -> InputData:
    """Build synthetic input data using the project's helper."""
    seed = config.SEED if config.SEED is not None else 42
    return build_input(config, DAYS=config.DAYS, N=config.N, seed=seed)


def run_solver(
    config: Config | None = None,
    data: InputData | None = None,
    input_builder: InputBuilder | None = None,
    reporter: Reporter | None = None,
    progress_cb: cp_model.CpSolverSolutionCallback | None = None,
    validate_config: bool = True,
    enable_reporting: bool = True,
) -> SolveResult:
    """
    Build, solve, and optionally report on a rostering scenario.

    Parameters
    ----------
    config:
        The configuration for the run. Defaults to `rostering.config.cfg` when omitted.
    validate_config:
        Toggle to run `Config.validate()` before building inputs.
    data:
        Pre-built `InputData`. When omitted then `input_builder` (or the default synthetic
        builder) is used to construct data from the given config.
    input_builder:
        Optional callable that accepts a `Config` and returns `InputData`. Ignored when
        `data` is supplied.
    reporter:
        Custom reporter instance. When `enable_reporting` is True and no reporter is
        provided, the default `Reporter` is used. Set `enable_reporting=False` to skip
        pre/post solve hooks entirely.
    enable_reporting:
        When False, skips reporter pre/post hooks even if a reporter is provided.
    progress_cb:
        Optional `cp_model.CpSolverSolutionCallback` implementation. Defaults to
        `MinimalProgress`.

    Returns
    -------
    SolveResult
        Structured output from the solving phase.
    """
    cfg_obj = config or cfg

    if validate_config:
        cfg_obj.validate()
    cfg_obj.ensure_skill_grids()

    input_data = data
    if input_data is None:
        builder = input_builder or default_input_builder
        input_data = builder(cfg_obj)

    staff_count = len(getattr(input_data, "staff", []) or [])
    if staff_count and staff_count != int(cfg_obj.N):
        raise ValueError(
            f"Config.N={cfg_obj.N} but input data contains {staff_count} staff. "
            "Update the Config or data so they agree."
        )

    model = RosterModel(cfg_obj, input_data)

    active_reporter = reporter if enable_reporting else None
    if active_reporter is None and enable_reporting:
        active_reporter = Reporter(cfg_obj)

    if active_reporter is not None:
        active_reporter.pre_solve(model)

    model.build()

    progress = progress_cb or MinimalProgress(
        cfg_obj.TIME_LIMIT_SEC, cfg_obj.LOG_SOLUTIONS_FREQUENCY_SECONDS
    )
    result = model.solve(progress_cb=progress)

    if active_reporter is not None:
        active_reporter.post_solve(result, input_data)

    return result


def main() -> SolveResult:
    """CLI entry point retained for backwards compatibility."""
    return run_solver(
        config=cfg,
        validate_config=True,
        input_builder=default_input_builder,
        reporter=Reporter(cfg),
        enable_reporting=True,
        progress_cb=MinimalProgress(
            cfg.TIME_LIMIT_SEC, cfg.LOG_SOLUTIONS_FREQUENCY_SECONDS
        ),
    )


if __name__ == "__main__":
    main()
