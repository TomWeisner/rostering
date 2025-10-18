# tests/test_progress.py
import re
from unittest.mock import patch

import pytest
from ortools.sat.python import cp_model

from rostering.progress import MinimalProgress


@pytest.fixture
def solver():
    """CpSolver with a short time limit so the test runs fast."""
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = 0.2
    s.parameters.log_search_progress = False
    return s


@pytest.fixture
def callback():
    """
    MinimalProgress that logs on the first solution.
    Set log_every_sec=0 so the first solution triggers a print immediately.
    """
    return MinimalProgress(time_limit_sec=0.2, log_every_sec=0.0)


@pytest.fixture
def mock_print():
    """Patch print in the progress module to capture output."""
    with patch("rostering.progress.print") as m:
        yield m


def build_tiny_model():
    """
    Small model with an objective to encourage multiple improving solutions.
    Maximize x + y subject to bounds.
    """
    m = cp_model.CpModel()
    x = m.NewIntVar(0, 50, "x")
    y = m.NewIntVar(0, 50, "y")
    m.Maximize(x + y)
    return m


def test_progress_callback_is_called(solver, callback, mock_print):
    # Arrange
    model = build_tiny_model()

    # Act: run the solver with the callback
    status = solver.SolveWithSolutionCallback(model, callback)

    # Assert: solver ran and callback printed at least once
    assert status in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
        cp_model.INFEASIBLE,
        cp_model.UNKNOWN,
    )

    assert mock_print.call_count >= 1, "Expected MinimalProgress to print at least once"

    # Optional: verify a sane log format without overfitting on exact numbers
    args, _ = mock_print.call_args  # last call
    line = args[0] if args else ""
    # Example expected fields: "[  0.1s] sols=... | best=... | bound=..."
    assert "sols=" in line
    assert "best=" in line
    assert "bound=" in line
    assert "gap=" in line
    # starts with bracketed seconds
    assert re.match(r"^\[\s*\d+(\.\d+)?s\]\s", line)
