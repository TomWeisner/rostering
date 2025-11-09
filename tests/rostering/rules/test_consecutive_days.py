from __future__ import annotations

from types import SimpleNamespace

from ortools.sat.python import cp_model

from rostering.config import Config
from rostering.generate.staff import Staff
from rostering.input_data import InputData
from rostering.rules.consecutive_days import ConsecutiveDaysRule


def _make_ctx(n: int = 2, days: int = 3) -> SimpleNamespace:
    cfg = Config(
        N=n,
        DAYS=days,
        HOURS=24,
        START_DATE=__import__("datetime").datetime(2024, 1, 1),
        MIN_SHIFT_HOURS=1,
        MAX_SHIFT_HOURS=12,
        REST_HOURS=0,
        TIME_LIMIT_SEC=1.0,
        NUM_PARALLEL_WORKERS=1,
        LOG_SOLUTIONS_FREQUENCY_SECONDS=1.0,
        ENABLE_UNSAT_CORE=False,
    )
    staff = [
        Staff(
            id=i,
            name=f"S{i}",
            band=1,
            skills=["ANY"],
            is_night_worker=False,
            max_consec_days=2 if i == 0 else None,
        )
        for i in range(n)
    ]
    allowed = [[True for _ in range(cfg.HOURS)] for _ in range(cfg.N)]
    data = InputData(staff=staff, cfg=cfg, allowed=allowed)
    model = cp_model.CpModel()
    x = {
        (e, d, h): model.NewBoolVar(f"x_{e}_{d}_{h}")
        for e in range(cfg.N)
        for d in range(cfg.DAYS)
        for h in range(cfg.HOURS)
    }
    z = {
        (e, d): model.NewBoolVar(f"z_{e}_{d}")
        for e in range(cfg.N)
        for d in range(cfg.DAYS)
    }
    return SimpleNamespace(cfg=cfg, data=data, m=model, x=x, z=z)


def test_consecutive_days_rule_emits_penalties_and_runlen():
    ctx = _make_ctx()
    rule = ConsecutiveDaysRule(
        ctx,
        pref_free=1,
        base=2.0,
        scaler=1.0,
        scale_int=10,
    )
    rule.declare_vars()
    assert getattr(ctx, "consec_days_worked")

    rule.add_hard()  # Should not raise and should honor limits internally.
    terms = rule.contribute_objective()
    expected = ctx.cfg.N * max(0, ctx.cfg.DAYS - rule.pref_free)
    assert len(terms) == expected
