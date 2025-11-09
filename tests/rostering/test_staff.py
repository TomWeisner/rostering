from __future__ import annotations

from datetime import date, datetime

import pytest

from rostering.staff import Staff


def test_staff_adds_any_skill_and_deduplicates() -> None:
    staffer = Staff(
        id=1,
        name="Example",
        band=1,
        skills=["Python", "ANY", "Python"],
        is_night_worker=False,
    )
    assert staffer.skills == ["Python", "ANY"]

    another = Staff(
        id=2,
        name="Example 2",
        band=1,
        skills=[],
        is_night_worker=False,
    )
    assert another.skills == ["ANY"]


def test_staff_normalizes_date_sets() -> None:
    staffer = Staff(
        id=3,
        name="Dates",
        band=1,
        skills=["ANY"],
        holidays={date(2024, 1, 1), datetime(2024, 1, 2, 3, 0)},
        preferred_off={datetime(2024, 2, 3, 12, 0)},
    )
    assert staffer.holidays == {date(2024, 1, 1), date(2024, 1, 2)}
    assert staffer.preferred_off == {date(2024, 2, 3)}


def test_staff_raises_on_invalid_dates() -> None:
    with pytest.raises(TypeError):
        Staff(
            id=4,
            name="BadDates",
            band=2,
            skills=["ANY"],
            holidays={"not-a-date"},  # type: ignore[arg-type]
        )
