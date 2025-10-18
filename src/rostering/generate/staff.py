# staff_generation.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

# If you store a large list of first names in another module:
from rostering.generate.staff_names import FIRST_NAMES


# ----------------------------
# Configuration container
# ----------------------------
@dataclass(slots=True)
class StaffGenConfig:
    n: int = 100
    # Band distribution (must sum to 1.0)
    bands: Tuple[int, ...] = (1, 2, 3, 4)
    band_probs: Tuple[float, ...] = (0.70, 0.25, 0.04, 0.01)
    # Skill probabilities by band: dict[band] -> (pA, pB), independent Bernoullis
    skill_probs: dict[int, Tuple[float, float]] = field(
        default_factory=lambda: {
            1: (0.50, 0.50),
            2: (0.65, 0.40),
            3: (0.80, 0.30),
            4: (0.20, 0.01),
        }
    )
    # Night worker fraction
    night_worker_pct: float = 0.30
    # Fraction with a consecutive-days cap and cap-choice distribution
    capped_pct: float = 0.10
    cap_choices: Tuple[int, ...] = (3, 4, 5)
    cap_weights: Tuple[float, ...] = (0.3, 0.4, 0.3)

    # Time-off parameters
    holiday_rate: float = 0.10  # per-person, per-day prob of hard holiday
    pref_off_rate: float = 0.15  # per-person, per-day prob of soft preference

    # Rule 16 edges (nights 18–06; day spill and night spill)
    night_start: int = 18  # inclusive
    night_end: int = 6  # exclusive in wrap sense (0..6)
    night_into_day_slack: int = 2  # night workers can extend 2h into day
    day_into_night_slack: int = 1  # day workers can extend 1h into night

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
    id: int
    name: str
    band: int
    skillA: bool
    skillB: bool
    is_night_worker: bool
    consec_cap: Optional[int]
    holidays: set[int] = field(default_factory=set)
    pref_off: set[int] = field(default_factory=set)

    def __repr__(self) -> str:
        flags = []
        if self.skillA:
            flags.append("A")
        if self.skillB:
            flags.append("B")
        cap = f"cap={self.consec_cap}" if self.consec_cap is not None else "cap=∞"
        return (
            f"Staff(id={self.id}, name='{self.name}', band={self.band}, "
            f"skills={''.join(flags) or '-'}, night={self.is_night_worker}, {cap}, "
            f"hol={sorted(self.holidays)}, pref={sorted(self.pref_off)})"
        )


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
        # pick the 'shortfall' largest remainders to bump up
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

        staff.append(
            Staff(
                id=i,
                name=str(FIRST_NAMES[i]),
                band=b,
                skillA=hasA,
                skillB=hasB,
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

    :param staff: list of Staff objects to assign time off to.
    :param days: Number of days to consider for time off.
    :param holiday_rate: Probability of a day being a holiday (0 <= holiday_rate <= 1).
    :param pref_off_rate: Probability of a day being a preferred day off (0 <= pref_off_rate <= 1).
    :param seed: Optional seed for random number generator. Defaults to 7.
    """
    if days <= 0:
        raise ValueError("days must be > 0")
    if not (0.0 <= holiday_rate <= 1.0 and 0.0 <= pref_off_rate <= 1.0):
        raise ValueError("holiday_rate and pref_off_rate must be in [0,1].")
    g = _rng(seed)
    for s in staff:
        hol_idx = np.where(g.random(days) < holiday_rate)[0].tolist()
        pref_idx = np.where(g.random(days) < pref_off_rate)[0].tolist()
        # soft prefs cannot overlap hard holidays
        pref = set(pref_idx) - set(hol_idx)
        s.holidays = set(hol_idx)
        s.pref_off = pref


def allowed_hours_for_staff(
    s: Staff,
    night_start: int = 18,
    night_end: int = 6,
    night_into_day_slack: int = 2,
    day_into_night_slack: int = 1,
) -> list[bool]:
    """
    Build a 24-length boolean mask of allowed hours for a staff member, honoring rule 16:
    - Night workers: nights are 18:00–06:00; they may extend into day by `night_into_day_slack` hours.
    - Day workers: days are 06:00–18:00; they may extend into night by `day_into_night_slack` hours.
    """
    if not (0 <= night_start <= 23) or not (0 <= night_end <= 23):
        raise ValueError("night_start/night_end must be within [0..23].")
    allow = [False] * 24

    def mark_range(start: int, end_excl: int):
        """Mark [start, end_excl) modulo 24 as allowed."""
        h = start
        while True:
            allow[h] = True
            h = (h + 1) % 24
            if h == end_excl % 24:
                break

    # canonical day window
    day_start, day_end = 6, 18  # 06:00–18:00
    # canonical night window wraps: 18:00–24:00 and 00:00–06:00
    n_start, n_end = night_start, night_end

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

    # normalize indexes >=24 back into 0..23 (mark_range already wraps modulo 24)
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
    bands: dict[int, float] = {}
    A = sum(s.skillA for s in staff)
    B = sum(s.skillB for s in staff)
    night = sum(s.is_night_worker for s in staff)
    capped = sum(1 for s in staff if s.consec_cap is not None)
    for s in staff:
        bands[s.band] = bands.get(s.band, 0) + 1
    return {
        "N": n,
        "bands": bands,
        "skillA_pct": A / n if n else 0.0,
        "skillB_pct": B / n if n else 0.0,
        "night_pct": night / n if n else 0.0,
        "capped_pct": capped / n if n else 0.0,
    }


def staff_to_dataframe(staff: list[Staff]) -> pd.DataFrame:
    import pandas as pd

    rows = []
    for s in staff:
        rows.append(
            {
                "id": s.id,
                "name": s.name,
                "band": s.band,
                "skillA": bool(s.skillA),
                "skillB": bool(s.skillB),
                "is_night_worker": bool(s.is_night_worker),
                "consec_cap": s.consec_cap if s.consec_cap is not None else np.nan,
                "holidays": sorted(s.holidays),
                "pref_off": sorted(s.pref_off),
            }
        )
    return pd.DataFrame(rows)


# ----------------------------
# Demo / CLI
# ----------------------------
if __name__ == "__main__":
    # Example usage
    DAYS = 7
    cfg = StaffGenConfig(
        n=100,
        seed=7,
        holiday_rate=0.10,
        pref_off_rate=0.05,
        night_into_day_slack=2,
        day_into_night_slack=1,
    )
    cfg.validate()

    # Create staff
    staff = create_staff(cfg)

    # Assign time off for this horizon
    assign_time_off(
        staff,
        days=DAYS,
        holiday_rate=cfg.holiday_rate,
        pref_off_rate=cfg.pref_off_rate,
        seed=cfg.seed,
    )

    # Build availability masks
    allowed = build_allowed_matrix(staff, cfg)

    # Print a quick sample + summary
    print(staff[0])
    print(staff[1])
    print(staff[2])

    summary = staff_summary(staff)
    print("\nSummary:")
    for k, v in summary.items():
        v_sorted = sorted(v) if isinstance(v, dict) else v
        print(f"  {k}: {v_sorted}")

    # Optional: dump to DataFrame
    try:
        import pandas as pd

        df = staff_to_dataframe(staff)
        print("\nHead:")
        print(df.head(5).to_string(index=False))
    except Exception:
        pass
