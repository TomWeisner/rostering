from __future__ import annotations

from types import SimpleNamespace

from ortools.sat.python import cp_model

from rostering.config import Config
from rostering.generate.staff import Staff
from rostering.input_data import InputData
from rostering.rules.band_shortfall import BandShortfallPenaltyRule


def _make_staff_member(idx: int, band: int) -> Staff:
    return Staff(
        id=idx,
        name=f"Staff {idx}",
        band=band,
        skills=["ANY"],
        is_night_worker=False,
        max_consec_days=None,
        holidays=set(),
        preferred_off=set(),
    )


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
        _make_staff_member(0, band=1),
        _make_staff_member(1, band=2),
        _make_staff_member(2, band=3),
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


def test_band_shortfall_penalty_adds_terms_for_high_bands():
    ctx = _make_ctx()
    rule = BandShortfallPenaltyRule(
        ctx,
        base=1.3,
        scale=1.0,
        band_base=1.25,
    )
    terms = rule.contribute_objective()
    assert terms, "Expected penalty terms to be generated for high-band staff."
    assert len(terms) == 2  # one penalty per high-band employee
