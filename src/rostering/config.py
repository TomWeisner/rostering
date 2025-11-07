from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal, Optional, TypeAlias, cast

SkillGrid: TypeAlias = list[list[dict[str, int]]]


@dataclass
class Config:

    # Number of employees
    N: int

    # Planning horizon
    DAYS: int = 7
    HOURS: int = 24
    START_DATE: datetime = datetime(2025, 10, 13)  # Monday

    ### HARD CONSTRAINTS ###

    # Shift rules
    MIN_SHIFT_HOURS: int = 0
    MAX_SHIFT_HOURS: int = 18

    # Rest
    REST_HOURS: int = 12  # set 0 to diagnose without rest

    # Skills requiring certain coverage minimums (or maximums)
    SKILL_MIN: Optional[SkillGrid] = None
    SKILL_MAX: Optional[SkillGrid] = None

    ### SOFT PENALTIES ###

    # Consecutive days worked
    RUN_PEN_PREF_FREE: int = 5
    RUN_PEN_BASE: float = 2.0
    RUN_PEN_SCALER: float = 1.0
    RUN_PEN_SCALE_INT: int = 1000

    # Fairness
    FAIRNESS_BASE: float = 1.4
    FAIRNESS_SCALE: float = 1.0
    FAIRNESS_MAX_DEVIATION_HOURS: int = 45

    WEEKLY_MAX_HOURS: Optional[int] = 40  # None = disable

    ### SOLVER SETUP ###

    # Solver
    TIME_LIMIT_SEC: float = 60.0
    NUM_PARALLEL_WORKERS: int = 1
    LOG_SOLUTIONS_FREQUENCY_SECONDS: float = 5.0

    # Diagnostics
    ENABLE_UNSAT_CORE: bool = True

    # Detailed logging for employees with these IDs
    INSPECT_EMPLOYEE_IDS: list[int] = field(default_factory=lambda: [0, 1, 17])

    # RANDOM SEED
    SEED: Optional[int] = None

    def validate(self):
        """
        Validate the Config object has sensible values before solving.
        """
        if not (0 < self.MIN_SHIFT_HOURS <= self.MAX_SHIFT_HOURS <= self.HOURS):
            raise ValueError("Require 0 < MIN_SHIFT_HOURS <= MAX_SHIFT_HOURS <= HOURS.")
        if not (0 <= self.REST_HOURS <= self.HOURS):
            raise ValueError("REST_HOURS must be in [0, HOURS].")
        if self.RUN_PEN_BASE < 1.0:
            raise ValueError("RUN_PEN_BASE must be >= 1.0.")
        if (
            self.WEEKLY_MAX_HOURS is not None
            and self.WEEKLY_MAX_HOURS > self.DAYS * self.HOURS
        ):
            raise ValueError("WEEKLY_MAX_HOURS too large for horizon.")
        if self.TIME_LIMIT_SEC <= 0.0:
            raise ValueError("TIME_LIMIT_SEC must be > 0.")
        if self.NUM_PARALLEL_WORKERS <= 0:
            raise ValueError("NUM_PARALLEL_WORKERS must be > 0.")


def _ensure_grids(C: Config) -> None:
    if getattr(C, "SKILL_MIN", None) is None:
        C.SKILL_MIN = [[{} for _ in range(C.HOURS)] for _ in range(C.DAYS)]
    if getattr(C, "SKILL_MAX", None) is None:
        C.SKILL_MAX = [[{} for _ in range(C.HOURS)] for _ in range(C.DAYS)]


def require_skill_everywhere(
    C: Config, skill: str, k: int = 1, mode: Literal["min", "max"] = "min"
) -> None:
    if mode not in ("min", "max"):
        raise ValueError("mode must be 'min' or 'max'")
    _ensure_grids(C)
    min_grid: SkillGrid = cast(SkillGrid, C.SKILL_MIN)
    max_grid: SkillGrid = cast(SkillGrid, C.SKILL_MAX)
    for d in range(C.DAYS):
        for h in range(C.HOURS):
            if mode == "min":
                cur = min_grid[d][h].get(skill, 0)
                min_grid[d][h][skill] = max(cur, k)
            elif mode == "max":
                cur = max_grid[d][h].get(skill, 0)
                max_grid[d][h][skill] = max(cur, k)


def require_skill_in_slots(
    C: Config,
    skill: str,
    days: Iterable[int] | range | Callable[[int], bool] | None = None,
    hours: Iterable[int] | range | Callable[[int], bool] | None = None,
    k: int = 1,
    mode: Literal["min", "max"] = "min",
) -> None:
    if mode not in ("min", "max"):
        raise ValueError("mode must be 'min' or 'max'")

    _ensure_grids(C)
    min_grid: SkillGrid = cast(SkillGrid, C.SKILL_MIN)
    max_grid: SkillGrid = cast(SkillGrid, C.SKILL_MAX)

    day_ok = _to_pred(days, C.DAYS)
    hour_ok = _to_pred(hours, C.HOURS)

    for d in range(C.DAYS):
        if not day_ok(d):
            continue
        for h in range(C.HOURS):
            if not hour_ok(h):
                continue
            if mode == "min":
                cur = min_grid[d][h].get(skill, 0)
                min_grid[d][h][skill] = max(cur, k)
            elif mode == "max":
                cur = max_grid[d][h].get(skill, 0)
                max_grid[d][h][skill] = max(cur, k)


def hours_between(
    start: float, end: float, *, period: int = 24
) -> Callable[[int], bool]:
    """
    Start inclusive, end exclusive, wrapping on 'period'.
    Works with float boundaries (e.g., 22.5 to 6.0). Predicate takes int hour index.
    """
    start = float(start) % period
    end = float(end) % period
    length = (end - start) % period
    return lambda h: 0 <= h < period and ((h - start) % period) < length


def _to_pred(
    sel: Iterable[int] | range | Callable[[int], bool] | None,
    size: int,
) -> Callable[[int], bool]:
    """
    Normalize selection to a predicate over [0, size).
    - None => all indices
    - callable => bounds-checked application
    - iterable/range => membership test
    """
    if sel is None:
        return lambda i: 0 <= i < size
    if callable(sel):
        return lambda i: 0 <= i < size and bool(sel(i))
    # iterable/range path
    idx_set = {int(i) for i in sel}
    return lambda i: 0 <= i < size and (i in idx_set)


cfg = Config(
    HOURS=24,
    DAYS=6,
    START_DATE=datetime(2023, 1, 1),
    N=50,
    MIN_SHIFT_HOURS=4,
    MAX_SHIFT_HOURS=12,
    REST_HOURS=12,
    RUN_PEN_PREF_FREE=5,
    RUN_PEN_BASE=2.0,
    RUN_PEN_SCALER=1.0,
    RUN_PEN_SCALE_INT=10,
    FAIRNESS_BASE=1.25,
    FAIRNESS_SCALE=100,
    FAIRNESS_MAX_DEVIATION_HOURS=15,
    WEEKLY_MAX_HOURS=40,
    TIME_LIMIT_SEC=10.0,
    NUM_PARALLEL_WORKERS=12,
    LOG_SOLUTIONS_FREQUENCY_SECONDS=5.0,
    ENABLE_UNSAT_CORE=True,
    INSPECT_EMPLOYEE_IDS=field(default_factory=lambda: [0, 1, 17]),
    SEED=3,
)

# always have 5+ staff working
require_skill_everywhere(C=cfg, skill="ANY", k=5, mode="min")

# always have 1+ senior staff
require_skill_everywhere(C=cfg, skill="SENIOR", k=1, mode="min")

overnight_hours = hours_between(start=22, end=6, period=cfg.HOURS)
day_hours = hours_between(start=6, end=22, period=cfg.HOURS)

# require 2+ staff working overnight with skill A
# but require 3+ staff during the day working with skill A
require_skill_in_slots(C=cfg, skill="A", hours=overnight_hours, k=2, mode="min")
require_skill_in_slots(C=cfg, skill="A", hours=day_hours, k=3, mode="min")

# always have 1+ staff working overnight with skill B
# but require 2+ staff during the day working with skill B
require_skill_in_slots(C=cfg, skill="B", hours=overnight_hours, k=1, mode="min")
require_skill_in_slots(C=cfg, skill="B", hours=day_hours, k=2, mode="min")
