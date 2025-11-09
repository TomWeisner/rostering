from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Callable, Sequence, Type

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch
from ortools.sat.python import cp_model

from rostering.config import Config, cfg
from rostering.generate.staff import Staff
from rostering.input_data import InputData, build_input
from rostering.model import RosterModel
from rostering.progress import MinimalProgress
from rostering.reporting import Reporter
from rostering.result_types import SolveResult
from rostering.rules.base import Rule, RuleSpec

InputBuilder = Callable[[Config], InputData]


def default_input_builder(config: Config) -> InputData:
    """Build synthetic input data using the project's helper."""
    seed = config.SEED if config.SEED is not None else 42
    return build_input(config, DAYS=config.DAYS, N=config.N, seed=seed)


def run_solver(
    config: Config | None = None,
    data: InputData | None = None,
    input_builder: InputBuilder | None = None,
    reporter: Reporter | None = None,
    progress_cb: cp_model.CpSolverSolutionCallback | None = None,
    validate_config: bool = True,
    enable_reporting: bool = True,
    rules: Sequence[RuleSpec | Type[Rule]] | None = None,
) -> SolveResult:
    """
    Build, solve, and optionally report on a rostering scenario.

    Parameters
    ----------
    config:
        The configuration for the run. Defaults to `rostering.config.cfg` when omitted.
    validate_config:
        Toggle to run `Config.validate()` before building inputs.
    data:
        Pre-built `InputData`. When omitted then `input_builder` (or the default synthetic
        builder) is used to construct data from the given config.
    input_builder:
        Optional callable that accepts a `Config` and returns `InputData`. Ignored when
        `data` is supplied.
    reporter:
        Custom reporter instance. When `enable_reporting` is True and no reporter is
        provided, the default `Reporter` is used. Set `enable_reporting=False` to skip
        pre/post solve hooks entirely.
    enable_reporting:
        When False, skips reporter pre/post hooks even if a reporter is provided.
    progress_cb:
        Optional `cp_model.CpSolverSolutionCallback` implementation. Defaults to
        `MinimalProgress`.
    rules:
        Optional iterable describing which rule classes to use (and any per-rule
        penalty/weight settings). `None` falls back to the library defaults.

    Returns
    -------
    SolveResult
        Structured output from the solving phase.
    """
    cfg_obj = config or cfg

    if validate_config:
        cfg_obj.validate()
    cfg_obj.ensure_skill_grids()

    input_data = data
    if input_data is None:
        builder = input_builder or default_input_builder
        input_data = builder(cfg_obj)

    staff_count = len(getattr(input_data, "staff", []) or [])
    if staff_count and staff_count != int(cfg_obj.N):
        raise ValueError(
            f"Config.N={cfg_obj.N} but input data contains {staff_count} staff. "
            "Update the Config or data so they agree."
        )

    model = RosterModel(cfg_obj, input_data, rules=rules)

    active_reporter = reporter if enable_reporting else None
    if active_reporter is None and enable_reporting:
        active_reporter = Reporter(cfg_obj)

    if active_reporter is not None:
        active_reporter.pre_solve(model, stage="precheck")

    model.build()
    if active_reporter is not None:
        active_reporter.pre_solve(
            model,
            stage="model_stats",
            model_stats=model.model_stats(),
        )

    progress = progress_cb or MinimalProgress(
        cfg_obj.TIME_LIMIT_SEC, cfg_obj.LOG_SOLUTIONS_FREQUENCY_SECONDS
    )
    result = model.solve(progress_cb=progress)

    if active_reporter is not None:
        active_reporter.post_solve(result, input_data)

    _export_shift_reports(result, cfg_obj, input_data)

    return result


def main() -> SolveResult:
    """CLI entry point retained for backwards compatibility."""
    return run_solver(
        config=cfg,
        validate_config=True,
        input_builder=default_input_builder,
        reporter=Reporter(cfg),
        enable_reporting=True,
        progress_cb=MinimalProgress(
            cfg.TIME_LIMIT_SEC, cfg.LOG_SOLUTIONS_FREQUENCY_SECONDS
        ),
    )


if __name__ == "__main__":
    main()


def _export_shift_reports(res: SolveResult, cfg: Config, data: InputData) -> None:
    df_sched = getattr(res, "df_sched", None)
    if df_sched is None or df_sched.empty:
        return

    df = df_sched.copy()
    df["scheduled"] = 1
    df["date"] = pd.to_datetime(df["date"])
    df["employee_id"] = df["employee_id"].astype(int)

    dates = pd.date_range(cfg.START_DATE.date(), periods=cfg.DAYS, freq="D")
    hours = pd.Index(range(cfg.HOURS), name="hour")
    idx = pd.MultiIndex.from_product([dates, hours], names=["date", "hour"])

    def _label(i: int, staff: Staff) -> str:
        base = getattr(staff, "name", "") or f"Employee {i}"
        return base

    counts: dict[str, int] = defaultdict(int)
    column_labels: list[str] = []
    column_staff: list[Staff] = []
    for i, staff in enumerate(data.staff):
        label = _label(i, staff)
        counts[label] += 1
        final_label = label if counts[label] == 1 else f"{label} ({counts[label]})"
        column_labels.append(final_label)
        column_staff.append(staff)

    hourly = (
        df.pivot_table(
            index=["date", "hour"],
            columns="employee_id",
            values="scheduled",
            aggfunc="max",
            fill_value=0,
        )
        .reindex(index=idx, fill_value=0)
        .reindex(columns=range(len(column_labels)), fill_value=0)
    )
    hourly.columns = column_labels

    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    hourly.to_csv(out_dir / "shifts_hourly.csv")

    # aggregate by day, number of hours scheduled for each day for each staff
    daily = hourly.groupby(level="date").sum()
    daily.to_csv(out_dir / "shifts_daily.csv")

    _export_hourly_gantt(hourly, column_staff, cfg)


def _export_hourly_gantt(
    hourly: pd.DataFrame, staff: list[Staff], cfg: Config, max_employees: int = 10
) -> None:
    if hourly.empty or not staff:
        return

    num_staff = min(max_employees, hourly.shape[1], len(staff))
    if num_staff == 0:
        return

    rng = random.Random(cfg.SEED if cfg.SEED is not None else 42)
    available_indices = list(range(min(hourly.shape[1], len(staff))))
    rng.shuffle(available_indices)
    chosen_indices = sorted(available_indices[:num_staff])

    sample_cols = [hourly.columns[i] for i in chosen_indices]
    sample_staff = [staff[i] for i in chosen_indices]

    date_index = pd.to_datetime(hourly.index.get_level_values("date"))
    hour_index = pd.to_timedelta(hourly.index.get_level_values("hour"), unit="h")
    timestamps = date_index + hour_index

    sample = hourly[sample_cols].copy()
    sample.index = pd.DatetimeIndex(timestamps, name="timestamp")

    band_sequence = [getattr(member, "band", None) for member in sample_staff]
    bands_sorted = sorted({band for band in band_sequence if band is not None})
    none_present = any(band is None for band in band_sequence)

    gradient = LinearSegmentedColormap.from_list(
        "green_blue_purple",
        ["#6EE7B7", "#34D399", "#3B82F6", "#6366F1", "#C4B5FD"],
    )
    color_map: dict[int, tuple[float, float, float, float]] = {}
    if bands_sorted:
        denom = max(len(bands_sorted) - 1, 1)
        for idx, band in enumerate(bands_sorted):
            color_map[band] = gradient(idx / denom)
    default_color = "#94a3b8"

    fig_height = 3 + num_staff * 0.2
    fig, ax = plt.subplots(figsize=(9, fig_height), dpi=150)

    hour_width = 1 / 24  # Matplotlib date numbers are in days.
    y_positions = list(range(num_staff))[::-1]
    for idx, column in enumerate(sample_cols):
        staff_obj = sample_staff[idx]
        color = color_map.get(staff_obj.band, default_color)
        y = y_positions[idx]
        scheduled_hours = sample[column][sample[column] >= 1]

        if scheduled_hours.empty:
            continue

        for ts in scheduled_hours.index:
            ax.barh(
                y,
                width=hour_width,
                left=mdates.date2num(ts),
                height=0.8,
                color=color,
                align="center",
                linewidth=0,
                alpha=0.9,
                zorder=3,
            )

    ax.set_yticks(y_positions, sample_cols)
    ax.set_ylabel("Employee")
    ax.set_xlabel("Time of shift")
    ax.set_title(f"Sample employee shifts (up to {num_staff} employees)", fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))

    start = timestamps.min()
    end = timestamps.max() + pd.Timedelta(hours=1)
    ax.set_xlim(mdates.date2num(start), mdates.date2num(end))

    day_start = start.normalize()
    day_end = (end + pd.Timedelta(hours=1)).normalize()
    day_ticks = pd.date_range(day_start, day_end, freq="D")
    for dt in day_ticks:
        ax.axvline(
            mdates.date2num(dt), color="0.85", linestyle="--", linewidth=0.8, zorder=1
        )

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ax.set_ylim(-0.5, num_staff - 0.5)

    def _band_label(band: int | None) -> str:
        return f"Band {band}" if band is not None else "Band N/A"

    legend_handles = [
        Patch(facecolor=color_map.get(band, default_color), label=_band_label(band))
        for band in bands_sorted
    ]
    if none_present:
        legend_handles.append(Patch(facecolor=default_color, label="Band N/A"))
    if legend_handles:
        ax.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.2),
            ncol=3,
            frameon=False,
        )

    ax.grid(False)
    fig.tight_layout()
    out_path = Path("outputs/example_shifts_gantt.png")
    fig.savefig(out_path, dpi=fig.dpi, bbox_inches="tight")
    plt.show()
