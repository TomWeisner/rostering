from dataclasses import dataclass
from datetime import timedelta

# Your staff generator
from rostering.generate.staff import (
    StaffGenConfig,
    assign_time_off,
    build_allowed_matrix,
    create_staff,
)


@dataclass
class InputData:
    staff: list
    allowed: list[list[bool]]  # shape: (N, 24)
    is_weekend: list[bool]  # length DAYS
    public_holidays: set  # day-index set


def build_input(cfg, DAYS: int, N: int, seed: int = 7) -> InputData:
    # weekend mask
    dates = [cfg.START_DATE + timedelta(days=d) for d in range(DAYS)]
    is_weekend = [dt.weekday() >= 5 for dt in dates]

    # staff + availability
    gen_cfg = StaffGenConfig(
        n=N,
        seed=seed,
        holiday_rate=0.10,
        pref_off_rate=0.05,
        night_into_day_slack=2,
        day_into_night_slack=1,
    )
    gen_cfg.validate()

    staff = create_staff(gen_cfg)
    assign_time_off(
        staff,
        days=DAYS,
        holiday_rate=gen_cfg.holiday_rate,
        pref_off_rate=gen_cfg.pref_off_rate,
        seed=gen_cfg.seed,
    )
    allowed_np = build_allowed_matrix(staff, gen_cfg)  # (N, 24) ndarray[bool]
    allowed: list[list[bool]] = allowed_np.astype(bool).tolist()

    return InputData(
        staff=staff,
        allowed=allowed,
        is_weekend=is_weekend,
        public_holidays=set(),  # use cfg.PUBLIC_HOLIDAYS in model construction
    )
