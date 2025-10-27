from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal, Optional, TypeAlias, cast

SkillGrid: TypeAlias = list[list[dict[str, int]]]


@dataclass
class Config:
    # Horizon
    DAYS: int = 7
    HOURS: int = 24
    START_DATE: datetime = datetime(2025, 10, 13)  # Monday

    # Workforce & demand
    N: int = 100

    # Shift rules
    MIN_SHIFT_H: int = 4
    MAX_SHIFT_H: int = 12

    SKILL_MIN: Optional[SkillGrid] = None
    SKILL_MAX: Optional[SkillGrid] = None

    # Rest
    REST_HOURS: int = 12  # set 0 to diagnose without rest

    # Soft penalties: consecutive days worked
    RUN_PEN_PREF_FREE: int = 5
    RUN_PEN_BASE: float = 2.0
    RUN_PEN_SCALER: float = 1.0
    RUN_PEN_SCALE_INT: int = 1000

    # Fairness
    FAIRNESS_WEIGHT_PER_HOUR: int = 50  # integer weight
    FAIRNESS_DEV_CAP: int = 40  # how many deviation tiers to model
    FAIRNESS_TIER_WEIGHT: float = 10

    WEEKLY_MAX_HOURS: Optional[int] = 40  # None = disable

    # Solver
    TIME_LIMIT_SEC: float = 150.0
    NUM_WORKERS: int = 12
    LOG_EVERY_SEC: float = 5.0

    # Diagnostics
    PRINT_PRECHECK_EXAMPLES: int = 5
    ENABLE_UNSAT_CORE: bool = True
    PRINT_POSTSUM_HEAD: int = 10

    # Inspect
    INSPECT_EMPLOYEE_IDS: list[int] = field(default_factory=lambda: [0, 1, 17])

    def validate(self):
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
    MIN_SHIFT_H=4,
    MAX_SHIFT_H=12,
    REST_HOURS=12,
    RUN_PEN_PREF_FREE=5,
    RUN_PEN_BASE=2.0,
    RUN_PEN_SCALER=1.0,
    RUN_PEN_SCALE_INT=10,
    FAIRNESS_WEIGHT_PER_HOUR=5,
    FAIRNESS_DEV_CAP=40,
    FAIRNESS_TIER_WEIGHT=1,
    WEEKLY_MAX_HOURS=40,
    TIME_LIMIT_SEC=15.0,
    NUM_WORKERS=12,
    LOG_EVERY_SEC=5.0,
    PRINT_PRECHECK_EXAMPLES=5,
    ENABLE_UNSAT_CORE=True,
    PRINT_POSTSUM_HEAD=10,
    INSPECT_EMPLOYEE_IDS=field(default_factory=lambda: [0, 1, 17]),
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
