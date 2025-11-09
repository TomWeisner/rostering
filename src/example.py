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
from rostering.config import (
    hours_between,
    require_skill_everywhere,
    require_skill_in_slots,
)
from rostering.generate.staff import staff_from_json
from rostering.main import MinimalProgress, Reporter, default_input_builder
from rostering.rules.availability import AvailabilityRule
from rostering.rules.base import RuleSpec
from rostering.rules.coverage import CoverageRule
from rostering.rules.decision_variables import VariablesRule
from rostering.rules.fairness import FairnessRule
from rostering.rules.min_length_shift import MinShiftLengthRule
from rostering.rules.rest import RestRule
from rostering.rules.shift_interval import ShiftIntervalRule
from rostering.rules.weekly_cap import WeeklyCapRule
from rostering.staff import Staff

cfg = Config(
    N=32,
    DAYS=7,
    HOURS=24,
    START_DATE=datetime(2024, 1, 1),
    MIN_SHIFT_HOURS=4,
    MAX_SHIFT_HOURS=12,
    NIGHT_SHIFT_START=18,
    REST_HOURS=12,
    TIME_LIMIT_SEC=10.0,
    NUM_PARALLEL_WORKERS=4,
    LOG_SOLUTIONS_FREQUENCY_SECONDS=5.0,
)


def _example_rule_specs() -> list[RuleSpec]:
    """Lightweight rule set for option 3 (keeps fairness simple)."""
    return [
        RuleSpec(cls=VariablesRule, order=0),
        RuleSpec(cls=AvailabilityRule, order=10),
        RuleSpec(cls=ShiftIntervalRule, order=20),
        RuleSpec(cls=MinShiftLengthRule, order=40),
        RuleSpec(cls=RestRule, order=50),
        RuleSpec(cls=CoverageRule, order=60),
        RuleSpec(cls=WeeklyCapRule, order=70),
        RuleSpec(
            cls=FairnessRule,
            order=90,
            settings={
                "base": 1.25,
                "scale": 1.0,
                "max_deviation_hours": 6,
            },
        ),
    ]


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

        run_solver(
            cfg,
            data=InputData(staff=staff, cfg=cfg),
        )

    # Run the code with custom staff data defined via JSON. Typical production use.
    elif option == 3:

        staff = staff_from_json(Path("src/example_staff.json"))
        cfg.N = len(staff)
        cfg.TIME_LIMIT_SEC = 30
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
        run_solver(
            cfg, data=InputData(staff=staff, cfg=cfg), rules=_example_rule_specs()
        )
    else:
        raise SystemExit(f"Unknown option {option}")


def main() -> None:
    args = parse_args()
    run_option(args.option)


if __name__ == "__main__":
    main()
