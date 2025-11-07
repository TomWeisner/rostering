from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import matplotlib.pyplot as plt

from rostering.input_data import InputData

from .adapters import ResultAdapter
from .metrics import avg_staffing_by_hour_and_skill


def _save_and_show(fig: plt.Figure, filename: str) -> None:
    """Persist the plot under figures/ and show it."""
    out_dir = Path("figures")
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
    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    for i, (skill, series) in enumerate(per_skill.items()):
        if skill == "ANY":
            continue
        vals = [float(series.loc[h]) for h in hours]
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
    ax.set_xlim(-0.5, len(hours) - 0.5)

    ax.plot(
        hours,
        [float(overall.loc[h]) for h in hours],
        linewidth=2.5,
        color="black",
        label="Staff",
    )

    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Avg num SKILLS covered")
    ax.set_xticks(hours)
    ax.legend(title="Skill", ncol=2)
    fig.tight_layout()
    _save_and_show(fig, "hour_of_day_skill_bar_chart.png")


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

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    ax.plot(
        solution_idx, best_vals, label="Best objective", color="tab:blue", linewidth=1.5
    )
    ax.plot(
        solution_idx,
        bound_vals,
        label="Solver lower bound",
        color="tab:red",
        linestyle="--",
        linewidth=1.25,
    )
    ax.set_xlabel("Solution # (in discovery order)")
    ax.set_ylabel("Penalty")
    ax.set_xlim(0, len(history) + 1)

    ax_time = ax.twinx()
    ax_time.plot(
        solution_idx,
        times,
        label="Elapsed time (s)",
        color="tab:green",
        linewidth=1.5,
        alpha=0.7,
    )
    ax_time.set_ylabel("Elapsed time (s)")

    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax_time.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save_and_show(fig, "solution_progress.png")
