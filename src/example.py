"""
Module with example code for running the rostering solver.

There are three ways to run the code:

1. Run the code with default options. This will generate
    synthetic staff data from the config and run the solver for these.
2. Run the code with custom staff data defined via code.
3. Run the code with custom staff data pre-defined in a JSON file.

Usage via cli:
    python3 -m src.example --option 1
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from rostering import Config, InputData, run_solver
from rostering.main import MinimalProgress, Reporter, default_input_builder

cfg = Config(
    N=32,
    DAYS=7,
    HOURS=24,
    START_DATE=datetime(2024, 1, 1),
    MIN_SHIFT_HOURS=4,
    MAX_SHIFT_HOURS=12,
    REST_HOURS=12,
    TIME_LIMIT_SEC=10.0,
    NUM_PARALLEL_WORKERS=1,
    LOG_SOLUTIONS_FREQUENCY_SECONDS=5.0,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rostering examples.")
    parser.add_argument(
        "--option",
        type=int,
        default=3,
        choices=(1, 2, 3),
        help="Example scenario to run (default: 3).",
    )
    return parser.parse_args()


def run_option(option: int) -> None:
    print(f"Running example code with option {option}")

    # Run the code with default options. This will generate
    # synthetic staff data from the config and run the solver for these.
    if option == 1:

        # The parameters below are defaults, with the exception of config,
        # they can be ommitted i.e. the below is equivalent to:
        # run_solver(cfg)
        run_solver(
            config=cfg,
            validate_config=True,
            input_builder=default_input_builder,
            reporter=Reporter(cfg),
            enable_reporting=True,
            progress_cb=MinimalProgress(
                cfg.TIME_LIMIT_SEC, cfg.LOG_SOLUTIONS_FREQUENCY_SECONDS
            ),
        )

    # Run the code with custom staff data defined via code.
    elif option == 2:
        from rostering.generate.staff import Staff

        base = cfg.START_DATE.date()

        staff = [
            Staff(
                id=0,
                name="A",
                band=1,
                skills=[],
                max_consec_days=None,
                is_night_worker=False,
                holidays={base + timedelta(days=offset) for offset in (2, 4, 6)},
            ),
            Staff(
                id=1,
                name="B",
                band=2,
                skills=["PYTHON", "FIRST_AID"],
                max_consec_days=3,
                is_night_worker=True,
                holidays=set(),
            ),
        ]

        run_solver(cfg, data=InputData(staff=staff, cfg=cfg))

    # Run the code with custom staff data defined via JSON. Typical production use.
    elif option == 3:
        from rostering.config import (
            hours_between,
            require_skill_everywhere,
            require_skill_in_slots,
        )
        from rostering.generate.staff import staff_from_json

        staff = staff_from_json(Path("src/example_staff.json"))
        cfg.N = len(staff)
        require_skill_everywhere(cfg, "Python", k=1)
        require_skill_in_slots(
            cfg,
            "First Aid",
            days=None,
            hours=range(6, 18),
            k=2,
        )
        require_skill_in_slots(
            cfg,
            "First Aid",
            days=None,
            hours=hours_between(18, 6),
            k=1,
        )
        run_solver(cfg, data=InputData(staff=staff, cfg=cfg))
    else:
        raise SystemExit(f"Unknown option {option}")


def main() -> None:
    args = parse_args()
    run_option(args.option)


if __name__ == "__main__":
    main()
