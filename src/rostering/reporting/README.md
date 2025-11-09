# Reporting subsystem

Transforms solver output into concise text plus lightweight visuals that end up in `outputs/report.pdf`.

| Module | Responsibility |
| --- | --- |
| `adapters.py` | `ResultAdapter` protocol + `PandasResultAdapter` bridge `SolveResult` into the DataFrame views that reporters expect. |
| `data_models.py` | Small DTOs (`SlotRequirement`, `SlotGap`, `CoverageMetrics`) reused by metrics and renderers. |
| `metrics.py` | Pure helpers for coverage checks, slot gaps, fairness summaries, etc. |
| `plots.py` | Matplotlib views (hour-of-day stacked bars, solution-progress chart). Both save into the active `ReportDocument`. |
| `model_stats.py` | Formatting helpers that turn CP-SAT model / solver stats into the short summaries printed in the CLI report. |
| `text_report.py` | Owns the console/PDF text rendering plus the `ReportDocument` context that aggregates all prints + plots into `outputs/report.pdf`. |
| `reporter.py` | High-level orchestrator: runs the model pre-check, prints text summaries, optionally invokes plots (skipped entirely when the solver status is not FEASIBLE/OPTIMAL). |

Flow inside `Reporter.post_solve`:

1. Format and print model solver stats with `model_stats.format_solver_stats`.
2. If the run produced a trusted schedule, open a `ReportDocument`, call `render_text_report`, then append plots if `enable_plots=True`.
3. Close the document which writes the combined PDF under `outputs/`.

Adding new output:

1. Put reusable calculations in `metrics.py`.
2. Render text in `text_report.py` and/or figures in `plots.py`.
3. Kick off the new view from `reporter.py` so CLI callers get it automatically (non-feasible runs should remain quiet).***
