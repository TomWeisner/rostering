from datetime import datetime

from rostering.config import Config
from rostering.generate.staff import Staff
from rostering.input_data import InputData
from rostering.main import run_solver


def test_max_consecutive_days_rule_enforces_employee_cap():
    cfg = Config(
        N=1,
        DAYS=2,
        HOURS=4,
        START_DATE=datetime(2024, 1, 1),
        MIN_SHIFT_HOURS=1,
        MAX_SHIFT_HOURS=1,
        REST_HOURS=0,
        TIME_LIMIT_SEC=2.0,
        NUM_PARALLEL_WORKERS=1,
        LOG_SOLUTIONS_FREQUENCY_SECONDS=1.0,
    )
    cfg.DEFAULT_MIN_STAFF = 0  # avoid auto-demand; we'll set specific slots
    cfg.WEEKLY_MAX_HOURS = None
    cfg.ensure_skill_grids()
    for d in range(cfg.DAYS):
        cfg.SKILL_MIN[d][0]["ANY"] = 1  # demand at hour 0 each day

    staff = [
        Staff(
            id=0,
            name="Only",
            band=1,
            skills=["ANY"],
            is_night_worker=False,
            max_consec_days=1,
        )
    ]
    data = InputData(
        staff=staff,
        allowed=[[True] * cfg.HOURS],
    )

    res = run_solver(cfg, data=data, enable_reporting=False)
    assert res.status_name == "INFEASIBLE"
    assert res.unsat_core_groups, "Expected UNSAT core groups to be populated"
    assert any(
        key.startswith("MAX-CONSEC") for key in res.unsat_core_groups
    ), f"Unexpected UNSAT groups: {res.unsat_core_groups}"
