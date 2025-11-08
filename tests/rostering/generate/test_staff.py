from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

import rostering.generate.staff as staff_mod
from rostering.config import Config
from rostering.generate.staff import (
    Staff,
    StaffGenConfig,
    _deterministic_counts,
    allowed_hours_for_staff,
    assign_time_off,
    build_allowed_matrix,
    create_staff,
    staff_from_json,
    staff_summary,
)


def test_deterministic_counts_respects_total_and_rounding():
    """
    Verify that _deterministic_counts respects the total count and rounds to nearest integer
    while ensuring each count deviates from expectation by at most 1.
    """
    probs = np.array([0.2, 0.3, 0.5])
    counts = _deterministic_counts(5, probs)
    assert counts.sum() == 5
    # each count should deviate by at most 1 from expectation
    expected = probs * 5
    assert np.all(np.abs(counts - expected) <= 1.0)


def test_staff_config_validation_detects_invalid_probabilities():
    cfg = StaffGenConfig(band_probs=(0.3, 0.3, 0.3, 0.2))  # sums to 1.1
    with pytest.raises(ValueError, match="band_probs must sum to 1.0"):
        cfg.validate()


def test_create_staff_respects_band_and_skill_rules():
    """
    Verify that create_staff respects the band and skill rules specified in the
    configuration object. It should also ensure that every staff member has the
    "ANY" skill.

    This test creates a configuration object with two bands, each with a 50%
    probability of being assigned, and two skills, A and B. It then creates a
    list of four staff members using this configuration object. The test
    verifies that the resulting list has two staff members from each band,
    and that each staff member has the correct skills assigned to them.
    """
    cfg = StaffGenConfig(
        n=4,
        bands=(1, 2),
        band_probs=(0.5, 0.5),
        skill_probs={1: (1.0, 0.0), 2: (0.0, 1.0)},
        night_worker_pct=0.0,
        capped_pct=0.0,
        seed=123,
    )
    staff = create_staff(cfg)
    assert len(staff) == 4
    bands = [s.band for s in staff]
    assert bands.count(1) == 2
    assert bands.count(2) == 2

    for s in staff:
        assert "ANY" in s.skills
        if s.band == 1:
            assert "A" in s.skills and "B" not in s.skills
            assert "SENIOR" not in s.skills
        else:
            assert "B" in s.skills
            assert "SENIOR" in s.skills


def test_assign_time_off_never_overlaps(days: int = 5):
    """
    Verify that assign_time_off will never assign a holiday or preferred day off
    that overlaps with another already assigned holiday or preferred day off.
    """
    cfg = StaffGenConfig(n=2, seed=0)
    staff = create_staff(cfg)
    start = date(2024, 1, 1)
    assign_time_off(
        staff,
        days=days,
        holiday_rate=0.6,
        pref_off_rate=0.6,
        start_date=start,
        seed=1,
    )
    for s in staff:
        assert s.holidays.isdisjoint(s.preferred_off)
        assert all(isinstance(d, date) for d in s.holidays | s.preferred_off)
        assert all(0 <= (d - start).days < days for d in s.holidays | s.preferred_off)


def test_allowed_hours_day_vs_night_workers():
    """
    Verify that allowed_hours_for_staff correctly distinguishes between day and night workers.

    A day worker should be available from 06:00 to 18:00 and a night worker should be available
    from 18:00 to 06:00 the next day.
    """
    day_worker = Staff(
        id=0,
        name="Day",
        band=1,
        skills=["ANY"],
        is_night_worker=False,
        max_consec_days=None,
    )
    night_worker = Staff(
        id=1,
        name="Night",
        band=1,
        skills=["ANY"],
        is_night_worker=True,
        max_consec_days=None,
    )

    day_mask = allowed_hours_for_staff(day_worker)
    night_mask = allowed_hours_for_staff(night_worker)

    expected_day_hours = {6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}
    assert {h for h, allowed in enumerate(day_mask) if allowed} == expected_day_hours

    expected_night_hours = {18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7}
    assert {
        h for h, allowed in enumerate(night_mask) if allowed
    } == expected_night_hours


def test_build_allowed_matrix_matches_individual_masks():
    """
    Verify that build_allowed_matrix correctly constructs a matrix of allowed hours for a list of staff members.

    The matrix should have shape (N, 24) where N is the number of staff members, and each row should match
    the allowed hours for the corresponding staff member, as determined by allowed_hours_for_staff.
    """
    workers = [
        Staff(
            id=0,
            name="D",
            band=1,
            skills=["ANY"],
            is_night_worker=False,
            max_consec_days=None,
        ),
        Staff(
            id=1,
            name="N",
            band=1,
            skills=["ANY"],
            is_night_worker=True,
            max_consec_days=None,
        ),
    ]
    cfg = Config(N=2)
    mat = build_allowed_matrix(workers, cfg)
    assert mat.shape == (2, 24)
    assert np.array_equal(mat[0], allowed_hours_for_staff(workers[0]))
    assert np.array_equal(mat[1], allowed_hours_for_staff(workers[1]))


def test_staff_summary_returns_expected_fractions():
    """
    Verify that staff_summary returns the expected fractions for the given list of staff members.

    Tests that staff_summary returns the correct counts for the number of staff members,
    the number of each band, the percentage of staff members with each skill, and the percentage
    of staff members who are night workers or have a consecutive cap.
    """
    workers = [
        Staff(
            id=0,
            name="A",
            band=1,
            skills=["ANY", "A"],
            is_night_worker=False,
            max_consec_days=None,
        ),
        Staff(
            id=1,
            name="B",
            band=2,
            skills=["ANY", "B", "SENIOR"],
            is_night_worker=True,
            max_consec_days=4,
        ),
    ]
    summary = staff_summary(workers)
    assert summary["N"] == 2
    assert summary["bands"][1] == 1
    assert summary["bands"][2] == 1
    assert summary["skillA_pct"] == 0.5
    assert summary["skillB_pct"] == 0.5
    assert summary["senior_pct"] == 0.5
    assert summary["night_pct"] == 0.5
    assert summary["capped_pct"] == 0.5


def _write_staff_file(path: Path, entries: list[dict]) -> Path:
    path.write_text(json.dumps(entries))
    return path


def test_staff_from_json_reads_custom_file(tmp_path):
    path = _write_staff_file(
        tmp_path / "custom.json",
        [
            {
                "id": 1,
                "name": "Alice",
                "band": 2,
                "skills": ["A"],
                "is_night_worker": True,
                "max_consec_days": 4,
                "holidays": ["2024-01-02"],
                "preferred_off": ["2024-01-03"],
            },
            {
                "id": 2,
                "name": "Bob",
                "band": 1,
                "skills": ["B"],
            },
        ],
    )
    staff = staff_from_json(path)
    assert [s.name for s in staff] == ["Alice", "Bob"]
    assert staff[0].holidays == {date.fromisoformat("2024-01-02")}
    assert staff[0].preferred_off == {date.fromisoformat("2024-01-03")}
    assert staff[1].max_consec_days is None


def test_staff_from_json_uses_default_file_when_omitted(monkeypatch, tmp_path):
    default = tmp_path / "default.json"
    _write_staff_file(
        default,
        [
            {
                "id": 5,
                "name": "Default",
                "band": 3,
                "skills": ["X"],
            }
        ],
    )
    monkeypatch.setattr(staff_mod, "DEFAULT_STAFF_JSON", default)
    staff = staff_from_json()
    assert len(staff) == 1
    assert staff[0].name == "Default"


def test_staff_from_json_requires_json_file(tmp_path):
    bad_path = tmp_path / "not_json.txt"
    bad_path.write_text("[]")
    with pytest.raises(ValueError):
        staff_from_json(bad_path)

    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        staff_from_json(missing)
