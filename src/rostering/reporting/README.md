# Reporting subsystem

This package turns solver output into textual summaries and plots.

| Module | Responsibility |
| --- | --- |
| `adapters.py` | Defines `ResultAdapter` (protocol) and `PandasResultAdapter`, which normalise whatever the solver returns (`SolveResult` by default) into the data frames the reporters expect. |
| `data_models.py` | Lightweight dataclasses (`SlotRequirement`, `SlotGap`, `CoverageMetrics`) used throughout the reporting stack. |
| `metrics.py` | Pure functions that derive coverage statistics, slot gaps, and per-hour staffing averages from the model + solution. |
| `text_report.py` | Renders the console report (per-employee hours, coverage summary, slot gaps, etc.). |
| `plots.py` | Matplotlib helpers for hour-of-day coverage bars and the solution-progress plot; each figure is saved under `./figures/`. |
| `reporter.py` | Orchestrator used by `rostering.main`: runs the model pre-check (with a confirmation prompt if infeasible), prints the text report, and triggers plots when enabled. |

Typical flow inside `Reporter.post_solve`:

1. `render_text_report(...)` prints summaries.
2. `show_hour_of_day_histograms(...)` visualises stacked skill coverage by hour.
3. `show_solution_progress(...)` plots best objective vs. solver bound by solution index (using the progress history captured by `MinimalProgress`).

If you introduce a new reporting artefact:

- Add the core calculation to `metrics.py` if it produces reusable data.
- Keep view concerns in either `text_report.py` (for console output) or `plots.py` (for figures).
- Wire it up in `reporter.py` so CLI callers automatically get the new output.
