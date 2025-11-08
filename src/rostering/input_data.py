from dataclasses import dataclass

# Your staff generator
from rostering.generate.staff import (
    Staff,
    StaffGenConfig,
    assign_time_off,
    build_allowed_matrix,
    create_staff,
)


@dataclass
class InputData:
    staff: list[Staff]
    allowed: list[list[bool]]  # shape: (N, 24)


def build_input(cfg, DAYS: int, N: int, seed: int = 7) -> InputData:
    """
    Build an InputData object from a Config and additional parameters.

    Parameters:
    cfg (Config): the configuration to use
    DAYS (int): the number of days in the planning horizon
    N (int): the number of staff members to generate
    seed (int, optional): the random seed to use. Defaults to 7.

    Returns:
    InputData: the generated input data
    """
    # staff + availability
    gen_cfg = StaffGenConfig(
        n=N,
        seed=seed,
        holiday_rate=0.10,
        pref_off_rate=0.05,
    )
    gen_cfg.validate()

    staff = create_staff(gen_cfg)
    assign_time_off(
        staff,
        days=DAYS,
        holiday_rate=gen_cfg.holiday_rate,
        pref_off_rate=gen_cfg.pref_off_rate,
        start_date=cfg.START_DATE.date(),
        seed=gen_cfg.seed,
    )
    allowed_np = build_allowed_matrix(staff, cfg)  # (N, 24) ndarray[bool]
    allowed: list[list[bool]] = allowed_np.astype(bool).tolist()

    return InputData(
        staff=staff,
        allowed=allowed,
    )
