from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from rostering.input_data import InputData
from rostering.model import SolveResult
from rostering.reporting.adapters import PandasResultAdapter, ResultAdapter
from rostering.reporting.model_stats import format_model_stats, format_solver_stats
from rostering.reporting.plots import (
    show_hour_of_day_histograms,
    show_solution_progress,
)
from rostering.reporting.text_report import (
    ReportDocument,
    render_text_report,
    set_active_report,
)


class Reporter:
    """High-level orchestrator: runs pre-check confirmations and renders reports."""

    def __init__(
        self,
        cfg: Any,
        adapter: ResultAdapter | None = None,
        num_print_examples: int = 6,
        enable_plots: bool = True,
    ) -> None:
        """
        cfg must expose:
          - DAYS / HOURS
          - SKILL_MIN grid
          - allowed mask + staff holidays via InputData
        """
        self.cfg = cfg
        self.adapter: ResultAdapter = adapter or PandasResultAdapter()
        self.num_print_examples = num_print_examples
        self.enable_plots = enable_plots

    # ---------- Back-compat entry points ----------

    def pre_solve(
        self, model: object, *, stage: str = "precheck", model_stats: str | None = None
    ) -> None:
        """
        Run pre-check confirmation or log model stats depending on the stage.
        stage="precheck"  -> perform feasibility prompt.
        stage="model_stats" -> print model complexity summary if available.
        """
        if stage == "model_stats":
            summary = format_model_stats(model_stats)
            if summary:
                print("\nModel stats summary:\n" + summary)
            return

        precheck = getattr(model, "precheck", None)
        if not callable(precheck):
            print("Pre-check: (model has no `precheck()`; skipping)")
            return

        cap, dem, ok_cap, *_ = precheck()
        if not ok_cap:
            proceed = self._prompt_yes_no_default_yes(
                "Pre-check indicates infeasibility. Continue anyway?"
            )
            if not proceed:
                raise SystemExit("Stopped by user after infeasible pre-check.")

    def render_text_report(self, res: object, data: object) -> None:
        """Public entry point for callers that want text reporting only."""
        render_text_report(
            self.cfg,
            self.adapter,
            res,
            data,  # type: ignore[arg-type]
            num_print_examples=self.num_print_examples,
        )

    def post_solve(self, res: SolveResult, data: InputData) -> None:
        """Render textual report (and optional plots) after solving."""
        stats_summary = format_solver_stats(getattr(res, "solver_stats", None))
        if stats_summary:
            print("\nSolver stats summary:\n" + stats_summary)

        status = self.adapter.status_name(res)
        if status not in {"FEASIBLE", "OPTIMAL"}:
            return

        report_doc = ReportDocument(Path("outputs/report.pdf"))
        set_active_report(report_doc)
        try:
            self.render_text_report(res, data)
            if not self.enable_plots:
                return
            show_hour_of_day_histograms(
                self.cfg,
                res,
                data,
                self.adapter,
                enable_plot=self.enable_plots,
            )
            history = res.progress_history or []
            show_solution_progress(history=history)
        finally:
            set_active_report(None)
            report_doc.write()

    # ---------- helpers ----------

    def _prompt_yes_no_default_yes(self, msg: str) -> bool:
        """Prompt '[Y/n]' and return True for yes (default)."""
        try:
            if not sys.stdin or not sys.stdin.isatty():
                print(f"{msg} [Y/n] (non-interactive -> default: Y)")
                return True

            while True:
                resp = input(f"{msg} [Y/n]: ").strip().lower()
                if resp in ("", "y", "yes"):
                    return True
                if resp in ("n", "no"):
                    return False
                print("Please type 'y' or 'n'.")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted by user.")
            return False
