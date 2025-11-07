# staff_generation.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np
import pandas as pd

# If you store a large list of first names in another module:
from rostering.generate.staff_names import FIRST_NAMES


# ----------------------------
# Configuration container
# ----------------------------
@dataclass(slots=True)
class StaffGenConfig:
    """
    Configuration for generation of synthetic staff data.
    """

    n: int = 100

    # Band distribution (must sum to 1.0)
    bands: Tuple[int, ...] = (1, 2, 3, 4)

    band_probs: Tuple[float, ...] = (0.70, 0.25, 0.04, 0.01)

    # Skill probabilities by band: dict[band] -> (pA, pB)
    skill_probs: dict[int, Tuple[float, float]] = field(
        default_factory=lambda: {
            1: (0.50, 0.50),
            2: (0.65, 0.40),
            3: (0.80, 0.30),
            4: (0.20, 0.01),
        }
    )

    # Proportion of worksers who are night workers
    night_worker_pct: float = 0.30

    # Fraction of workers employed with a consecutive-days contract cap and cap-choice distribution
    capped_pct: float = 0.10
    cap_choices: Tuple[int, ...] = (3, 4, 5)
    cap_weights: Tuple[float, ...] = (0.3, 0.4, 0.3)

    # Time-off parameters
    holiday_rate: float = 0.10  # per-person, per-day prob of hard holiday
    pref_off_rate: float = (
        0.15  # per-person, per-day prob of soft preference for being off
    )

    # Times of day edges for shifts
    night_start: int = 18  # inclusive
    night_end: int = 6  # exclusive in wrap sense (0..6)
    night_into_day_slack: int = 2  # night workers can extend 2h into day period
    day_into_night_slack: int = 1  # day workers can extend 1h into night period

    # RNG seed
    seed: Optional[int] = 7

    def validate(self) -> None:
        if self.n <= 0:
            raise ValueError("n must be > 0.")
        if len(self.bands) != len(self.band_probs):
            raise ValueError("bands and band_probs must be same length.")
        if not np.isclose(sum(self.band_probs), 1.0, atol=1e-9):
            raise ValueError("band_probs must sum to 1.0")
        if set(self.bands) != set(self.skill_probs.keys()):
            raise ValueError("skill_probs must have entries for all bands.")
        for b, (pA, pB) in self.skill_probs.items():
            if not (0.0 <= pA <= 1.0) or not (0.0 <= pB <= 1.0):
                raise ValueError(f"Invalid skill probabilities for band {b}.")
        if not (0.0 <= self.night_worker_pct <= 1.0):
            raise ValueError("night_worker_pct must be in [0,1].")
        if not (0.0 <= self.capped_pct <= 1.0):
            raise ValueError("capped_pct must be in [0,1].")
        if len(self.cap_choices) != len(self.cap_weights):
            raise ValueError("cap_choices and cap_weights must be same length.")
        if any(c <= 0 for c in self.cap_choices):
            raise ValueError("cap_choices must be positive integers.")
        if not np.isclose(sum(self.cap_weights), 1.0, atol=1e-9):
            raise ValueError("cap_weights must sum to 1.0")
        for x in (self.holiday_rate, self.pref_off_rate):
            if not (0.0 <= x <= 1.0):
                raise ValueError("holiday_rate and pref_off_rate must be in [0,1].")
        for v in (self.night_start, self.night_end):
            if not (0 <= v <= 23):
                raise ValueError("night_start/night_end must be in [0..23].")
        if self.night_into_day_slack < 0 or self.day_into_night_slack < 0:
            raise ValueError("Slack values must be non-negative.")
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError("seed must be an int or None.")


# ----------------------------
# Data model
# ----------------------------
@dataclass(slots=True)
class Staff:
    """
    A staff member.
    """

    id: int
    name: str
    band: int
    skills: list[str]
    is_night_worker: bool
    consec_cap: Optional[int]
    holidays: set[int] = field(default_factory=set)
    pref_off: set[int] = field(default_factory=set)

    def __repr__(self) -> str:
        cap = f"cap={self.consec_cap}" if self.consec_cap is not None else "cap=∞"
        return (
            f"Staff(id={self.id}, name='{self.name}', band={self.band}, "
            f"skills={self.skills}, night={self.is_night_worker}, {cap}, "
            f"hol={sorted(self.holidays)}, pref={sorted(self.pref_off)})"
        )

    def __post_init__(self) -> None:
        # Ensure "ANY" is present exactly once.
        if "ANY" not in self.skills:
            self.skills.append("ANY")
        # De-duplicate while preserving order (small lists, so simple approach is fine)
        seen = set()
        dedup = []
        for s in self.skills:
            if s not in seen:
                seen.add(s)
                dedup.append(s)
        self.skills = dedup


# ----------------------------
# Generation helpers
# ----------------------------
def _rng(seed: Optional[int]) -> np.random.Generator:
    return np.random.default_rng(seed) if seed is not None else np.random.default_rng()


def _deterministic_counts(n: int, probs: np.ndarray) -> np.ndarray:
    """
    Turn probabilities into integer counts that sum to n with minimal rounding error.
    """
    expected = probs * n
    floors = np.floor(expected).astype(int)
    shortfall = n - floors.sum()
    if shortfall > 0:
        remainders = expected - floors
        bump_idx = np.argsort(remainders)[::-1][:shortfall]
        floors[bump_idx] += 1
    return floors


# ----------------------------
# Core API
# ----------------------------
def create_staff(cfg: StaffGenConfig) -> list[Staff]:
    cfg.validate()
    g = _rng(cfg.seed)

    if len(FIRST_NAMES) < cfg.n:
        raise ValueError(f"Not enough FIRST_NAMES ({len(FIRST_NAMES)}) for n={cfg.n}.")

    # Assign bands deterministically close to target distribution
    probs = np.array(cfg.band_probs, dtype=float)
    counts = _deterministic_counts(cfg.n, probs)
    band_values = np.concatenate(
        [np.full(count, band, dtype=int) for band, count in zip(cfg.bands, counts)]
    )
    g.shuffle(band_values)

    # Night flags & capped flags
    night_flags = g.random(cfg.n) < cfg.night_worker_pct
    capped_flags = g.random(cfg.n) < cfg.capped_pct
    cap_draws = g.choice(
        cfg.cap_choices, size=cfg.n, p=np.array(cfg.cap_weights, dtype=float)
    )

    staff: list[Staff] = []
    for i in range(cfg.n):
        b = int(band_values[i])
        pA, pB = cfg.skill_probs[b]
        hasA = bool(g.random() < pA)
        hasB = bool(g.random() < pB)
        consec_cap = int(cap_draws[i]) if capped_flags[i] else None

        skills: list[str] = []
        if hasA:
            skills.append("A")
        if hasB:
            skills.append("B")
        # Senior: anyone band >= 2
        if b >= 2:
            skills.append("SENIOR")

        staff.append(
            Staff(
                id=i,
                name=str(FIRST_NAMES[i]),
                band=b,
                skills=skills,
                is_night_worker=bool(night_flags[i]),
                consec_cap=consec_cap,
            )
        )
    return staff


def assign_time_off(
    staff: list[Staff],
    days: int,
    holiday_rate: float,
    pref_off_rate: float,
    seed: Optional[int] = 7,
) -> None:
    """
    Randomly assign holidays and preferred days off to a staff roster.
    """
    if days <= 0:
        raise ValueError("days must be > 0")
    if not (0.0 <= holiday_rate <= 1.0 and 0.0 <= pref_off_rate <= 1.0):
        raise ValueError("holiday_rate and pref_off_rate must be in [0,1].")
    g = _rng(seed)
    for s in staff:
        hol = set(np.where(g.random(days) < holiday_rate)[0])
        pref = set(np.where(g.random(days) < pref_off_rate)[0])
        # soft prefs cannot overlap hard holidays
        s.holidays = hol
        s.pref_off = pref - hol


def allowed_hours_for_staff(
    s: Staff,
    night_start: int = 18,
    night_end: int = 6,
    night_into_day_slack: int = 2,
    day_into_night_slack: int = 1,
) -> list[bool]:
    """
    Build a 24-length boolean mask of allowed hours for a staff member, honoring rule 16.
    """
    if not (0 <= night_start <= 23) or not (0 <= night_end <= 23):
        raise ValueError("night_start/night_end must be within [0..23].")
    allow = [False] * 24

    def mark_range(start: int, end_excl: int) -> None:
        """Mark [start, end_excl) modulo 24 as allowed."""
        steps = end_excl - start
        if steps <= 0:
            steps = 24
        for offset in range(steps):
            allow[(start + offset) % 24] = True

    # canonical day window
    day_start, day_end = 6, 18  # 06:00–18:00
    n_start, n_end = night_start, night_end  # night wraps

    if s.is_night_worker:
        # Core night
        mark_range(n_start, (n_end if n_end > n_start else n_end + 24))
        # Extra: night into day slack
        if night_into_day_slack > 0:
            mark_range(day_start, day_start + night_into_day_slack)
    else:
        # Core day
        mark_range(day_start, day_end)
        # Extra: day into night slack
        if day_into_night_slack > 0:
            mark_range(day_end, day_end + day_into_night_slack)

    return allow


# ----------------------------
# Convenience utilities
# ----------------------------
def build_allowed_matrix(staff: list[Staff], cfg: StaffGenConfig) -> np.ndarray:
    """Return (N, 24) boolean numpy array (dtype=bool)."""
    mat = np.zeros((len(staff), 24), dtype=bool)
    for e, s in enumerate(staff):
        mat[e, :] = np.array(
            allowed_hours_for_staff(
                s,
                cfg.night_start,
                cfg.night_end,
                cfg.night_into_day_slack,
                cfg.day_into_night_slack,
            ),
            dtype=bool,
        )
    return mat


def staff_summary(staff: list[Staff]) -> dict:
    n = len(staff)
    from collections import Counter

    bands = Counter(s.band for s in staff)
    A = sum("A" in s.skills for s in staff)
    B = sum("B" in s.skills for s in staff)
    SENIOR = sum("SENIOR" in s.skills for s in staff)
    night = sum(s.is_night_worker for s in staff)
    capped = sum(s.consec_cap is not None for s in staff)
    return {
        "N": n,
        "bands": bands,
        "skillA_pct": A / n if n else 0.0,
        "skillB_pct": B / n if n else 0.0,
        "senior_pct": SENIOR / n if n else 0.0,
        "night_pct": night / n if n else 0.0,
        "capped_pct": capped / n if n else 0.0,
    }


def staff_to_dataframe(staff: list[Staff]) -> pd.DataFrame:
    rows = []
    for s in staff:
        rows.append(
            {
                "id": s.id,
                "name": s.name,
                "band": s.band,
                "skillA": "A" in s.skills,
                "skillB": "B" in s.skills,
                "senior": "SENIOR" in s.skills,
                "is_night_worker": bool(s.is_night_worker),
                "consec_cap": s.consec_cap if s.consec_cap is not None else np.nan,
                "holidays": sorted(s.holidays),
                "pref_off": sorted(s.pref_off),
                "skills": s.skills[:],  # for debugging/inspection
            }
        )
    return pd.DataFrame(rows)
