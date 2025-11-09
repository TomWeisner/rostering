from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import matplotlib.pyplot as plt

from rostering.input_data import InputData

from .adapters import ResultAdapter
from .metrics import avg_staffing_by_hour_and_skill
from .text_report import get_active_report


def _save_and_show(fig: plt.Figure, filename: str) -> None:
    """Persist the plot under outputs/ and show it."""
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / filename, dpi=fig.dpi, bbox_inches="tight")
    plt.show()


def show_hour_of_day_histograms(
    cfg: Any,
    res: Any,
    data: InputData,
    adapter: ResultAdapter,
    enable_plot: bool = True,
) -> None:
    """Render stacked bar charts of skill coverage by hour-of-day."""
    if not enable_plot:
        return

    overall, per_skill = avg_staffing_by_hour_and_skill(cfg, res, data, adapter)
    if not per_skill:
        return

    import matplotlib.cm as cm

    hours = list(overall.index)
    cmap = cm.get_cmap("Pastel1")
    skills = list(per_skill.keys())
    colors = [cmap(i % cmap.N) for i in range(len(skills))]

    bottom = [0.0] * len(hours)
    fig, ax = plt.subplots(figsize=(7.5, 4), dpi=150)
    ax.set_title("Skill coverage by hour of day", pad=35)
    max_y_stack = 0.0
    for i, (skill, series) in enumerate(per_skill.items()):
        if skill == "ANY":
            continue
        vals = [float(series.loc[h]) for h in hours]
        max_y_stack += max(vals)
        ax.bar(
            hours,
            vals,
            bottom=bottom,
            label=skill,
            color=colors[i],
            alpha=0.8,
            width=0.9,
            edgecolor="none",
        )
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xlim(hours[0], hours[-1])
    ax.set_xmargin(0.0)
    ax.set_ymargin(0.0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ax.spines.values():
        spine.set_zorder(0)

    ax.plot(
        hours,
        [float(overall.loc[h]) for h in hours],
        linewidth=1,
        color="black",
        label="Staff on shift",
    )

    max_y = max(max_y_stack, float(overall.max()))
    ax.set_ylim(0, max_y * 1.05)

    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Avg num skills covered")
    ax.set_xticks(hours)
    ax.legend(
        ncol=i + 2,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.15),
        borderaxespad=0.3,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save_and_show(fig, "hour_of_day_skill_bar_chart.png")
    report = get_active_report()
    if report is not None:
        report.add_figure(fig)


def show_solution_progress(history: Sequence[tuple[float, float, float]]) -> None:
    """
    Plot the best objective/bound versus solution index and overlay elapsed time.

    history entries are (wall_time_sec, best_obj, bound).
    """
    if not history:
        return
    solution_idx = list(range(1, len(history) + 1))
    times = [pt[0] for pt in history]
    best_vals = [pt[1] for pt in history]
    bound_vals = [pt[2] for pt in history]

    fig, ax = plt.subplots(figsize=(7.5, 4), dpi=150)
    ax.set_title("Penalty (objective) history", pad=35)
    penalty_color = "tab:blue"
    bound_color = "tab:red"
    time_color = "tab:green"

    ax.plot(
        solution_idx, best_vals, label="Objective", color=penalty_color, linewidth=1.5
    )
    ax.plot(
        solution_idx,
        bound_vals,
        label="Estimated optimal solution",
        color=bound_color,
        linestyle="--",
        linewidth=1.25,
    )
    ax.set_xlabel("Solution # (in discovery order)")
    ax.set_ylabel(
        f"Smallest objective found. Min={min(bound_vals):.1f}", color=penalty_color
    )
    ax.tick_params(axis="y", colors=penalty_color)
    ax.spines["left"].set_color(penalty_color)
    ax.set_xlim(*_expand_limits(solution_idx, axis_padding=0.01))
    ax.set_ylim(*_expand_limits(best_vals + bound_vals))
    ax.set_xmargin(0.0)
    ax.set_ymargin(0.0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ax.spines.values():
        spine.set_zorder(0)

    ax_time = ax.twinx()
    ax_time.plot(
        solution_idx,
        times,
        label="Elapsed time",
        color=time_color,
        linewidth=1.5,
        alpha=0.7,
    )
    ax_time.set_ylabel(
        f"Elapsed time (seconds). Max={max(times):.1f}s", color=time_color
    )
    ax_time.tick_params(axis="y", colors=time_color)
    ax_time.spines["right"].set_color(time_color)
    ax_time.set_ylim(*_expand_limits(times))
    ax_time.spines["top"].set_visible(False)
    ax_time.spines["left"].set_visible(False)
    for spine in ax_time.spines.values():
        spine.set_zorder(0)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax_time.get_legend_handles_labels()
    ax.legend(
        lines + lines2,
        labels + labels2,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.15),
        ncol=3,
        borderaxespad=0.3,
    )
    ax.grid(alpha=0.3)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save_and_show(fig, "solution_progress.png")
    report = get_active_report()
    if report is not None:
        report.add_figure(fig)


def _expand_limits(
    values: Sequence[float], axis_padding: float = 0.05
) -> tuple[float, float]:
    lo = min(values)
    hi = max(values)
    if lo == hi:
        delta = max(abs(lo), 1.0) * max(axis_padding, 0.05)
        return lo - delta, hi + delta
    span = hi - lo
    pad = span * axis_padding
    return lo - pad, hi + pad
