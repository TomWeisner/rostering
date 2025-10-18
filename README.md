# 🕒 Shift Optimiser (`rostering`)

> Optimise colleague shift assignments based on employee holidays/preferences and business needs.
> Hard constraints are **enforced**, while undesirable combinations incur **penalties** that the optimiser **minimises**.

[🐍 TestPyPI](https://test.pypi.org/project/rostering/) • [💻 GitHub Repo](https://github.com/TomWeisner/rostering)

[![codecov](https://codecov.io/gh/TomWeisner/rostering/branch/dev_setup/graph/badge.svg?token=76IBOK4C18)](https://app.codecov.io/gh/TomWeisner/rostering?branch=dev_setup)
[![CI](https://github.com/TomWeisner/rostering/actions/workflows/tests.yml/badge.svg)](https://github.com/TomWeisner/rostering/actions/workflows/tests.yml)
[![TestPyPI version](https://img.shields.io/pypi/v/rostering?pypiBaseUrl=https%3A%2F%2Ftest.pypi.org\&label=TestPyPI\&color=orange)](https://test.pypi.org/project/rostering/)
[![Python versions](https://img.shields.io/pypi/pyversions/rostering?pypiBaseUrl=https%3A%2F%2Ftest.pypi.org)](https://test.pypi.org/project/rostering/)
[![License](https://img.shields.io/github/license/TomWeisner/rostering.svg)](LICENSE)

---

## ✨ Features

* **Hard constraints:** e.g. maximum consecutive nights, legal time limits, required coverage
* **Soft constraints with penalties:** e.g. avoid split shifts, overly long shifts, or preference mismatches
* **Fairness-aware objective:** tunable weights for equitable scheduling
* **Reproducible runs:** deterministic seeds for consistent results
* **Modern tooling:** Poetry for dependencies, Nox for automation, pre-commit hooks for quality

---

## 🧩 Installation

### Option 1 — via `pip`

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple rostering
```

### Option 2 — via `Poetry`

```bash
# One-time setup to add TestPyPI
poetry source add --priority explicit testpypi https://test.pypi.org/simple/

# Add the package
poetry add --source testpypi rostering
```

---

## 🤝 Contributing

### 1️⃣ Clone & Set Up

```bash
git clone https://github.com/TomWeisner/rostering.git
cd rostering
code .
```

### 2️⃣ Install dependencies

```bash
poetry install
poetry config virtualenvs.in-project true
source .venv/bin/activate
poetry run pre-commit install
```

### 3️⃣ Run tests

```bash
pytest -q
```

---

## 🧪 Development

### Adding dependencies

```bash
# Runtime dependencies
poetry add numpy

# Dev tools
poetry add --group dev black

# Test-only libraries
poetry add --group test pytest hypothesis
```

---

## ⚙️ Nox Automation

This project uses **[Nox](https://nox.thea.codes/)** (with [nox-poetry](https://nox-poetry.readthedocs.io/)) to automate linting, formatting, type checks, and testing in isolated virtual environments.

### Setup

```bash
poetry add --group dev nox nox-poetry
```

### Run sessions

```bash
nox -L            # list sessions
nox -s lint       # run a specific session
nox               # run all sessions
```

| Session          | Purpose              | Tools Used         |
| ---------------- | -------------------- | ------------------ |
| `format`         | Auto-format code     | black, isort       |
| `lint`           | Lint/style checks    | ruff, black, isort |
| `typecheck_mypy` | Static type checking | mypy               |
| `tests`          | Run unit tests       | pytest             |

---

## 💅 Pre-commit Hooks

**[pre-commit](https://pre-commit.com/)** ensures consistent formatting and catches common issues before commits.

### Setup

```bash
poetry install --with dev
poetry run pre-commit install

# Run manually
poetry run pre-commit run --all-files
```

### Hooks Overview

| Hook                     | Description                          |
| ------------------------ | ------------------------------------ |
| **Black**                | Formats code to PEP 8.               |
| **isort**                | Sorts imports into logical groups.   |
| **Ruff**                 | Fast linter replacing Flake8/pylint. |
| **Mypy**                 | Static type checking.                |
| **check-yaml**           | Validates YAML syntax.               |
| **end-of-file-fixer**    | Ensures a trailing newline.          |
| **trailing-whitespace**  | Removes stray spaces.                |
| **check-merge-conflict** | Detects unresolved merge conflicts.  |

---

## 🚀 Publishing to TestPyPI

1. Raise a PR into `dev`
2. Wait for GitHub Actions to pass — one action automatically uploads to TestPyPI a version of the package with an incremented version number
