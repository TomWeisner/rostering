from __future__ import annotations

from types import SimpleNamespace

from ortools.sat.python import cp_model

from rostering.config import Config
from rostering.input_data import InputData
from rostering.rules.fairness import FairnessRule
from rostering.staff import Staff


def _make_ctx() -> SimpleNamespace:
    cfg = Config(
        N=3,
        DAYS=1,
        HOURS=4,
        MIN_SHIFT_HOURS=1,
        MAX_SHIFT_HOURS=2,
        REST_HOURS=0,
        TIME_LIMIT_SEC=1.0,
        NUM_PARALLEL_WORKERS=1,
        LOG_SOLUTIONS_FREQUENCY_SECONDS=1.0,
    )
    staff = [
        Staff(id=0, name="Ben", band=1, skills=["ANY"]),
        Staff(id=1, name="Harry", band=2, skills=["ANY"]),
        Staff(id=2, name="Luke", band=3, skills=["ANY"]),
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

    return SimpleNamespace(cfg=cfg, data=data, m=model, x=x)


def test_fairness_adds_band_penalties_for_high_band_staff():
    ctx = _make_ctx()
    rule = FairnessRule(
        ctx,
        base=1.2,
        scale=1.0,
        max_deviation_hours=2,
        band_shortfall_base=1.25,
        band_shortfall_scale=0.5,
        band_shortfall_max_gap=2,
        band_shortfall_threshold=1,
    )
    terms = rule.contribute_objective()
    # Base fairness adds two terms per employee (dev + penalty)
    base_terms = ctx.cfg.N * 2
    # Threshold is inclusive, so all three bands receive an extra penalty term.
    assert len(terms) == base_terms + ctx.cfg.N
