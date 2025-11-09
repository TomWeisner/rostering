# 🕒 Shift Optimiser (`rostering`)

> Optimise colleague shift assignments based on employee holidays/preferences and business needs.
> Hard constraints are **enforced**, while undesirable combinations incur **penalties** that the optimiser **minimises**.

[🐍 TestPyPI](https://test.pypi.org/project/rostering/) • [💻 GitHub Repo](https://github.com/TomWeisner/rostering)

[![codecov](https://codecov.io/gh/TomWeisner/rostering/branch/master/graph/badge.svg?token=76IBOK4C18)](https://codecov.io/gh/TomWeisner/rostering)
[![CI](https://github.com/TomWeisner/rostering/actions/workflows/tests.yml/badge.svg)](https://github.com/TomWeisner/rostering/actions/workflows/tests.yml)
[![TestPyPI version](https://img.shields.io/pypi/v/rostering?pypiBaseUrl=https%3A%2F%2Ftest.pypi.org\&label=TestPyPI\&color=orange)](https://test.pypi.org/project/rostering/)
[![Python versions](https://img.shields.io/pypi/pyversions/rostering?pypiBaseUrl=https%3A%2F%2Ftest.pypi.org)](https://test.pypi.org/project/rostering/)
[![License](https://img.shields.io/github/license/TomWeisner/rostering.svg)](LICENSE)

---

## Contents

1. [Features](#-features)
2. [Quick start](#-quick-start)
3. [Example CLI (`src/example.py`)](#-example-cli-srcexamplepy)
4. [How the optimiser works](#-how-the-optimiser-works)
5. [Running & monitoring](#-running--monitoring)
6. [Project tooling](#-project-tooling)
7. [Contributing](#-contributing)
8. [Publishing](#-publishing-to-testpypi)

---

## ✨ Features

- **Hard constraints:** e.g. minimum rest between shifts, per-skill coverage, legal hour caps
- **Soft penalties:** tunable costs for preference mismatches, long runs, unfair hour distribution
- **Fairness-aware objective:** exponential tiers to rein in big hour discrepancies
- **Progress visibility:** console callback plus saved plots of solution quality vs. solve progress
- **Reproducibility:** deterministic seeds at every generation step
- **Modern tooling:** Poetry, Nox, Ruff, pre-commit, GitHub Actions

---

## 🚀 Quick start

### Installing the repo for use (choose one)

**pip / TestPyPI**

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple \
            rostering
```

**Poetry**

```bash
poetry source add --priority explicit testpypi https://test.pypi.org/simple/
poetry add --source testpypi rostering
```

### Cloning the repo for local development

```bash
git clone https://github.com/TomWeisner/rostering.git
cd rostering
poetry install
poetry config virtualenvs.in-project true
source .venv/bin/activate
poetry run pre-commit install
```

#### Run the solver

See `src/example.py` for using the `run_solver` method defined in `main.py`

What happens in `main.py`:

1. `rostering.config.cfg` is validated and used to generate synthetic staff/input data.
2. The CP-SAT model is built (`rostering.build` + rules in `rostering.rules.*`).
3. The solver runs with `MinimalProgress` printing progress and storing history.
4. `Reporter.post_solve` prints textual summaries and, via `produce_outputs`, saves artefacts under `outputs/`:
   - `report.pdf` containing the console report plus embedded plots
   - Hour-of-day coverage stacked bars
   - Best objective vs. solver bound (line plot) with elapsed-time overlay
   - Hourly and daily shift CSVs plus a sample Gantt figure

Everything is deterministic as long as you keep the default seeds in `Config` and `StaffGenConfig`.

---

## 🧪 Example CLI (`src/example.py`)

Want a ready-made demo? Run the bundled CLI:

```bash
python -m src.example --option 1  # or 2 / 3
```

Options:

| Option | Description |
| --- | --- |
| `1` | Synthetic staff generated from the current `Config`. |
| `2` | Staff defined in code explicitly for a tiny two-person scenario. |
| `3` | Loads `src/example_staff.json` (50 people with various skills) and applies realistic skill minima + a lightweight rule template. This is most similar to a production example. |

---

## 🧠 How the optimiser works

| Stage | Module(s) | Description |
| --- | --- | --- |
| **Config & data** | `rostering.config`, `rostering.generate.*` | Define planning horizon, penalties, coverage minima and create synthetic staff (skills, availability, preferences). |
| **Pre-check** | `rostering.precheck` | Quick feasibility check: capacity vs. demand, per-skill availability gaps, warning if no staff own a demanded skill. |
| **Model build** | `rostering.build`, `rostering.rules.*` | `BuildContext` wires decision variables (`y/S/L/x/z`), and each rule registers hard/soft constraints + objective terms. |
| **Solve** | `rostering.solver`, `rostering.progress` | CP-SAT searches for minimum-penalty rosters. `MinimalProgress` logs solutions, tracks wall-clock/obj history for plotting. UNSAT cores are translated back to readable rule names. |
| **Reporting** | `rostering/reporting/` package | Modular reporters compute coverage metrics, slot gaps, fairness stats, and render plots or textual summaries. |

Key rule highlights:

- `rest.py`, `weekly_cap.py`, `run_penalty.py`: enforce rest hours, weekly caps, and penalise long consecutive runs.
- `coverage.py`: ensures per-skill hour minima/maxima and links per-skill variables to hour-level work decisions.
- `objective.py`: bundles all penalty terms (fairness, run penalties, etc.) into the single CP objective.

---

## 📊 Running & monitoring

1. **Progress callback** – every `LOG_SOLUTIONS_FREQUENCY_SECONDS`:
   ```text
   [  3.0s] pct of time limit=20.00% | best=12,345 | ratio=1.050 | sols=3
   ```
   - `pct of time limit` = elapsed time vs. limit
   - `best` = best objective found so far (penalty total)
   - `ratio` = best / solver bound (closer to 1 → proven optimal)
   - `sols` = solution count

2. **Saved history** – `MinimalProgress.solution_history()` feeds the reporter so we can produce a *Solution progress plot*

3. **Textual report** – after solving, `Reporter.render_text_report` prints:
   - Per-employee hours and stats
   - Coverage metrics (`assigned_people_hours`, `skill_demand_hours`, coverage ratio)
   - Slot-gap table for headcount shortfalls
   - Objective value, fairness metrics, consecutive-day summaries

4. **Outputs** – `produce_outputs()` saves artefacts under `outputs/`:
   - `report.pdf` (text report + embedded plots)
   - `shifts_hourly.csv` / `shifts_daily.csv`
   - `example_shifts_gantt.png` (hourly Gantt using up to 10 random staff)
   - Additional plots mirrored below for reference:
     - Hour-of-day coverage:<br>
       <p><img src="src/example_hour_of_day_skill_bar_chart.png" width="420" alt="Hour-of-day coverage" /></p>
     - Solver progress:<br>
       <p><img src="src/example_solution_progress.png" width="420" alt="Solver progress" /></p>
     - Sample hourly Gantt:<br>
       <p><img src="src/example_shifts_gantt.png" width="420" alt="Sample Gantt" /></p>
   Remove or archive them between runs if you want a clean slate.

---

## 🧪 Project tooling

### Testing & linting (Nox)

```bash
nox -L            # list sessions
nox -s lint       # lint only
nox               # run everything (format, lint, typecheck, tests)
```

| Session | Purpose | Tools |
| --- | --- | --- |
| `format` | Auto-format code | black, isort |
| `lint` | Lint/style checks | ruff, black, isort |
| `typecheck_mypy` | Static typing | mypy |
| `tests` | Unit tests | pytest + coverage |

### Pre-commit

```bash
poetry run pre-commit install
poetry run pre-commit run --all-files
```

Hooks include Black, isort, Ruff, mypy, YAML checks, whitespace fixers, etc. (see `.pre-commit-config.yaml`).

### Dependency management

```bash
poetry add numpy            # runtime dep
poetry add --group dev ruff # dev-only dep
poetry add --group test pytest hypothesis
```

---

## 🤝 Contributing

1. Fork & clone
2. `poetry install && poetry run pre-commit install`
3. Create a feature branch
4. Add tests (`tests/` already has coverage for generators, reporting, solver progress, etc.)
5. Run `nox` locally before pushing
6. Open a PR against `dev`

Issues/feature requests welcome!

---

## 📦 Publishing to TestPyPI

1. Raise a PR into `dev`
2. GitHub Actions (`tests.yml`) runs lint/typecheck/tests and, on success, builds the wheel/sdist
3. The CI workflow publishes to TestPyPI with an incremented version number

Once satisfied, bump the real PyPI release separately (outside this repo’s automation).

---

## 📚 Helpful entry points

| Purpose | Module |
| --- | --- |
| Configure runs | `src/rostering/config.py` |
| Generate synthetic staff/data | `src/rostering/generate/` |
| Build/solve orchestration | `src/rostering/model.py` |
| Constraint rules | `src/rostering/rules/` |
| Progress callback | `src/rostering/progress.py` |
| Programmatic entry point | `rostering.run_solver` |
| Reporting | `src/rostering/reporting/` |

Happy rostering! 🗓️
