from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from rostering.config import Config
from rostering.input_data import InputData
from rostering.model import SolveResult
from rostering.staff import Staff


def produce_outputs(res: SolveResult, cfg: Config, data: InputData) -> None:
    """Persist hourly/daily CSVs plus a sample Gantt chart for solved rosters."""
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

    daily = hourly.groupby(level="date").sum()
    daily.to_csv(out_dir / "shifts_daily.csv")

    sample_employee_hourly_gantt_plot(hourly, column_staff, cfg)


def sample_employee_hourly_gantt_plot(
    hourly: pd.DataFrame, staff: list[Staff], cfg: Config, max_employees: int = 10
) -> None:
    if hourly.empty or not staff:
        return

    num_staff = min(max_employees, hourly.shape[1], len(staff))
    if num_staff == 0:
        return

    rng = random.Random(cfg.SEED if cfg.SEED is not None else 555)
    available_indices = list(range(min(hourly.shape[1], len(staff))))
    rng.shuffle(available_indices)
    chosen_indices = sorted(available_indices[:num_staff])

    sample_cols = [hourly.columns[i] for i in chosen_indices]
    sample_staff = [staff[i] for i in chosen_indices]
    # Sort chosen staff by band (descending so higher bands appear on top). Tie-break by name.
    sorted_pairs = sorted(
        zip(sample_staff, sample_cols),
        key=lambda pair: (
            (getattr(pair[0], "band", 0) or 0),
            getattr(pair[0], "name", ""),
        ),
        reverse=True,
    )
    sample_staff = [s for s, _ in sorted_pairs]
    sample_cols = [c for _, c in sorted_pairs]

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

    hour_width = 1 / 24
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
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

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
