from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from ortools.sat.python import cp_model

# Only import the type for static analysis; no runtime import, so no cycles.
if TYPE_CHECKING:
    from ..model import RosterModel


class Rule(ABC):
    """
    A plugin that contributes variables, constraints, and/or objective terms.
    Phases run in this order across all rules:
      1) declare_vars
      2) add_hard
      3) add_soft
      4) contribute_objective
    """

    #: smaller runs earlier; use to enforce dependencies
    order: int = 100
    #: if False, the rule is skipped (can be controlled by Config)
    enabled: bool = True
    #: a short name used in logs/UNSAT core tags
    name: str = "Rule"

    def __init__(self, model: "RosterModel"):
        self.model = model

    # ---- Phases ----
    def declare_vars(self) -> None:
        """Create decision/aux variables (no constraints)."""
        return

    def add_hard(self) -> None:
        """Add hard constraints."""
        return

    def add_soft(self) -> None:
        """Add soft constraints (e.g., indicator vars)."""
        return

    def contribute_objective(self) -> list[cp_model.LinearExpr]:
        """Return a list of linear penalty terms added to the objective."""
        return []
