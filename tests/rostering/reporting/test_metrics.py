from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from rostering.config import Config
from rostering.input_data import InputData
from rostering.reporting import data_models, metrics
from rostering.reporting.adapters import ResultAdapter
from rostering.staff import Staff


class StubAdapter(ResultAdapter):
    def __init__(
        self, sched: pd.DataFrame | None = None, shifts: pd.DataFrame | None = None
    ):
        self._sched = sched if sched is not None else pd.DataFrame()
        self._shifts = shifts if shifts is not None else pd.DataFrame()

    def status_name(self, res):  # pragma: no cover - unused
        return "FEASIBLE"

    def objective_value(self, res):  # pragma: no cover - unused
        return None

    def avg_consecutive_workday_run(self, res):  # pragma: no cover - unused
        return None

    def max_consecutive_workday_run(self, res):  # pragma: no cover - unused
        return None

    def df_emp(self, res):  # pragma: no cover - unused
        return pd.DataFrame()

    def df_sched(self, res):
        return self._sched

    def df_shifts(self, res):
        return self._shifts


def simple_cfg(skills: list[list[dict[str, int]]], hours: int) -> SimpleNamespace:
    # Ensure each day has an entry for every hour to match the reporting grid.
    normalized = [row + [{}] * (hours - len(row)) for row in skills]
    return SimpleNamespace(DAYS=len(normalized), HOURS=hours, SKILL_MIN=normalized)


def _input_cfg(n: int) -> Config:
    return Config(
        N=n,
        DAYS=1,
        HOURS=24,
        START_DATE=datetime(2024, 1, 1),
        MIN_SHIFT_HOURS=1,
        MAX_SHIFT_HOURS=1,
        REST_HOURS=0,
        TIME_LIMIT_SEC=1.0,
        NUM_PARALLEL_WORKERS=1,
        LOG_SOLUTIONS_FREQUENCY_SECONDS=1.0,
    )


def make_input(staff_skills: list[set[str]]) -> InputData:
    staff_objs = []
    for idx, skills in enumerate(staff_skills):
        staff_objs.append(
            Staff(
                id=idx,
                name=f"S{idx}",
                band=1,
                skills=list(skills) if skills else ["ANY"],
                is_night_worker=False,
                max_consec_days=None,
                holidays=set(),
                preferred_off=set(),
            )
        )
    cfg = _input_cfg(len(staff_objs))
    return InputData(staff=staff_objs, cfg=cfg)


def test_slot_requirements_builds_expected_grid():
    cfg = simple_cfg([[{"A": 2}, {"B": 1}]], hours=2)
    grid = metrics.slot_requirements(cfg)

    assert len(grid) == 1 and len(grid[0]) == 2
    assert grid[0][0] == data_models.SlotRequirement(
        required_people_for_slot=2, per_skill_minima={"A": 2}
    )
    assert grid[0][1].per_skill_minima == {"B": 1}


def test_assigned_sets_prefers_schedule_over_shifts():
    sched = pd.DataFrame({"employee_id": [1], "day": [0], "hour": [2]})
    shifts = pd.DataFrame({})
    adapter = StubAdapter(sched=sched, shifts=shifts)
    cfg = simple_cfg([[{}]], hours=4)
    assigned = metrics.assigned_sets(cfg, res=None, adapter=adapter)
    assert assigned[(0, 2)] == {1}


def test_compute_coverage_metrics_counts_supply_and_shortfalls():
    cfg = simple_cfg([[{"A": 1}]], hours=1)
    adapter = StubAdapter(
        sched=pd.DataFrame({"employee_id": [0], "day": [0], "hour": [0]})
    )
    data = make_input([{"A"}])
    res = SimpleNamespace()

    cov = metrics.compute_coverage_metrics(cfg, res, data, adapter)

    assert cov.skill_demand_hours == 1
    assert cov.assigned_people_hours == 1
    assert cov.covered_skills == 1
    assert cov.unmatched_assignments_on_demand == 0


def test_compute_slot_gaps_marks_unattainable_slots():
    cfg = simple_cfg([[{"A": 2}]], hours=1)
    adapter = StubAdapter(
        sched=pd.DataFrame({"employee_id": [0], "day": [0], "hour": [0]})
    )
    # Only one staff member available, so slot is unattainable
    staff = [
        Staff(
            id=0,
            name="Only",
            band=1,
            skills=["A"],
            is_night_worker=False,
            max_consec_days=None,
            holidays=set(),
            preferred_off=set(),
        )
    ]
    cfg_data = _input_cfg(len(staff))
    data = InputData(staff=staff, cfg=cfg_data)
    top, df = metrics.compute_slot_gaps(cfg, None, data, adapter, top=1)

    assert top[0].unattainable is True
    assert df.iloc[0]["deficit"] == 1


def test_avg_staffing_by_hour_and_skill_returns_series():
    cfg = simple_cfg([[{"A": 1}]], hours=2)
    adapter = StubAdapter(
        sched=pd.DataFrame(
            {
                "employee_id": [0, 0],
                "day": [0, 0],
                "hour": [0, 1],
            }
        )
    )
    data = make_input([{"A"}])

    overall, per_skill = metrics.avg_staffing_by_hour_and_skill(
        cfg, None, data, adapter
    )
    assert list(overall.index) == [0, 1]
    assert per_skill["A"].tolist() == [1.0, 1.0]
