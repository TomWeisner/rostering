"""python3 -m src.example"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from rostering import Config, InputData, run_solver

cfg = Config(
    N=32,
    DAYS=7,
    HOURS=8,
    START_DATE=datetime(2024, 1, 1),
    MIN_SHIFT_HOURS=4,
    MAX_SHIFT_HOURS=12,
    REST_HOURS=12,
    TIME_LIMIT_SEC=2.0,
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

    if option == 1:
        run_solver(cfg)

    elif option == 2:
        from rostering.generate.staff import Staff, build_allowed_matrix

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

        allowed = build_allowed_matrix(staff, cfg).astype(bool).tolist()
        run_solver(cfg, data=InputData(staff=staff, allowed=allowed))

    elif option == 3:
        from rostering.generate.staff import build_allowed_matrix, staff_from_json

        staff = staff_from_json(Path("src/example_staff.json"))
        cfg.N = len(staff)
        allowed = build_allowed_matrix(staff, cfg).astype(bool).tolist()
        run_solver(cfg, data=InputData(staff=staff, allowed=allowed))
    else:
        raise SystemExit(f"Unknown option {option}")


def main() -> None:
    args = parse_args()
    run_option(args.option)


if __name__ == "__main__":
    main()
