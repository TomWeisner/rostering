from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Set


@dataclass
class Config:
    # Horizon
    DAYS: int = 7
    HOURS: int = 24
    START_DATE: datetime = datetime(2025, 10, 13)  # Monday

    # Workforce & demand
    N: int = 100
    COVER: int = 4

    # Per-hour minima
    MIN_SENIOR: int = 1
    MIN_SKILL_A: int = 2
    MIN_SKILL_B: int = 1

    # Shift rules
    MIN_SHIFT_H: int = 4
    MAX_SHIFT_H: int = 12

    # Rest
    REST_HOURS: int = 12  # set 0 to diagnose without rest

    # Holidays (by day index)
    PUBLIC_HOLIDAYS: Set[int] = field(default_factory=set)

    # Soft penalties: consecutive days worked
    RUN_PEN_PREF_FREE: int = 5
    RUN_PEN_BASE: float = 2.0
    RUN_PEN_SCALER: float = 1.0
    RUN_PEN_SCALE_INT: int = 1000

    # Fairness
    ENABLE_FAIRNESS: bool = True
    FAIRNESS_WEIGHT_PER_HOUR: int = 50  # integer weight
    WEEKLY_MAX_HOURS: Optional[int] = 40  # None = disable

    # Solver
    TIME_LIMIT_SEC: float = 60.0
    NUM_WORKERS: int = 8
    LOG_EVERY_SEC: float = 5.0

    # Diagnostics
    PRINT_PRECHECK_EXAMPLES: int = 5
    ENABLE_UNSAT_CORE: bool = True
    PRINT_POSTSUM_HEAD: int = 12

    # Inspect
    INSPECT_EMPLOYEE_IDS: Iterable[int] = (0, 1, 17, 42)

    def validate(self):
        if self.COVER < max(self.MIN_SENIOR, self.MIN_SKILL_A, self.MIN_SKILL_B):
            raise ValueError("COVER below per-hour minima makes problem infeasible.")
        if not (0 < self.MIN_SHIFT_H <= self.MAX_SHIFT_H <= self.HOURS):
            raise ValueError("Require 0 < MIN_SHIFT_H <= MAX_SHIFT_H <= HOURS.")
        if not (0 <= self.REST_HOURS <= self.HOURS):
            raise ValueError("REST_HOURS must be in [0, HOURS].")
        if self.RUN_PEN_BASE < 1.0:
            raise ValueError("RUN_PEN_BASE must be >= 1.0.")
        if (
            self.WEEKLY_MAX_HOURS is not None
            and self.WEEKLY_MAX_HOURS > self.DAYS * self.HOURS
        ):
            raise ValueError("WEEKLY_MAX_HOURS too large for horizon.")
