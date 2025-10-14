# 🕒 Shift Optimiser (rostering)

> Optimise colleague shift assignments based on employee holidays/preferences and business needs.
> Hard constraints are **enforced**; undesirable combinations incur **penalties** that the optimizer **minimises**.

[📘 Docs](https://example.com/docs) • [🐍 PyPI](https://pypi.org/project/shift-optimizer-example/) • [💻 Repo](https://github.com/example/shift-optimizer)

## ✨ Features

- Hard constraints (e.g., maximum consecutive nights, legal time limits, required coverage)
- Soft constraints with penalties (e.g., avoid split shifts & undesirably long shifts, preference mismatches)
- Fairness-aware objective with tunable weights
- Reproducible runs and deterministic seeds
- Poetry for dependencies/packaging, Nox for formatting/linting/test tasks, pre-commit hooks

## 🚀 Quickstart

```bash
# 1) Get the code
git clone git clone https://github.com/TomWeisner/rostering.git
cd rostering
code .

# 2) Install Poetry-managed dep
poetry install

# 3) Activate venv
poetry config virtualenvs.in-project true
poetry install
source .venv/bin/activate

# 4) Run tests
pytest -q
```

## Making changes

### Adding new deps
```bash
# 1) # Add a runtime dependency
poetry add numpy

# Add dev-only tools
poetry add --group dev black

# Add test-only libs
poetry add --group test pytest hypothesis
```

### 🧪 Using Nox for Automation

This project uses **[Nox](https://nox.thea.codes/)** (with [nox-poetry](https://nox-poetry.readthedocs.io/)) to automate formatting, linting, type checking, and testing.  
Nox creates isolated virtual environments for each task, ensuring consistency and reproducibility.

#### ⚙️ Setup

Install `nox` and `nox-poetry` via:
```bash
poetry add --group dev nox nox-poetry
```

#### 🚀 Running Nox Sessions

To see all available sessions:
`nox -L`

Run a specific session:
`nox -s <session>` e.g. `nox -s lint`

Run all sessions sequentially:
`nox`

#### Session Overview
| Session           | Purpose                            | Tools Used                     |
|-------------------|------------------------------------|--------------------------------|
| `format`          | Auto-format code                   | black, isort                   |
| `lint`            | Lint and style checks              | ruff, black, isort             |
| `typecheck_mypy`  | Static type checking               | mypy, pytest                   |
| `tests`           | Run test suite                     | pytest                         |

