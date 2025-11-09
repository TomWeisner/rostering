from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Optional


def _normalize_date_set(values: Iterable[Any]) -> set[date]:
    out: set[date] = set()
    for val in values:
        if isinstance(val, date) and not isinstance(val, datetime):
            out.add(val)
        elif isinstance(val, datetime):
            out.add(val.date())
        else:
            raise TypeError(
                "Holidays/preferred_off entries must be datetime.date or datetime.datetime."
            )
    return out


@dataclass(slots=True)
class Staff:
    """
    Core data model representing an employee regardless of how they were created.
    """

    id: int
    name: str
    band: int
    skills: list[str]
    is_night_worker: bool = False
    max_consec_days: Optional[int] = None
    holidays: set[date] = field(default_factory=set)
    preferred_off: set[date] = field(default_factory=set)

    def __repr__(self) -> str:
        cap = (
            f"cap={self.max_consec_days}"
            if self.max_consec_days is not None
            else "cap=∞"
        )
        return (
            f"Staff(id={self.id}, name='{self.name}', band={self.band}, "
            f"skills={self.skills}, night={self.is_night_worker}, {cap}, "
            f"hol={[d.isoformat() for d in sorted(self.holidays)]}, "
            f"pref={[d.isoformat() for d in sorted(self.preferred_off)]})"
        )

    def __post_init__(self) -> None:
        self.holidays = _normalize_date_set(self.holidays)
        self.preferred_off = _normalize_date_set(self.preferred_off)
        if "ANY" not in self.skills:
            self.skills.append("ANY")
        seen = set()
        dedup: list[str] = []
        for skill in self.skills:
            if skill not in seen:
                seen.add(skill)
                dedup.append(skill)
        self.skills = dedup
