# tests/conftest.py
from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import pytest


# -----------------------------
# Global, deterministic seeding
# -----------------------------
@pytest.fixture(autouse=True, scope="session")
def _seed_everything() -> None:
    """
    Make tests deterministic across runs. If you need a different seed in a test,
    override locally.
    """
    seed = int(os.environ.get("PYTEST_SEED", "1234"))
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    if np is not None:  # pragma: no branch
        np.random.seed(seed)


# -----------------------------
# Path helpers
# -----------------------------
@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repository root (where pyproject.toml lives)."""
    # Adjust if your tests/ folder lives elsewhere.
    return Path(__file__).resolve().parents[1]
