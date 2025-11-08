# src/rostering/rules/base.py
from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from rostering.config import Config
    from rostering.input_data import InputData

from ortools.sat.python import cp_model


class BuildCtxProto(Protocol):
    m: cp_model.CpModel
    cfg: Config
    data: InputData
    x: dict[tuple[int, int, int], cp_model.IntVar]
    runlen: dict[tuple[int, int], cp_model.IntVar]

    def add_assumption(self, label: str) -> cp_model.IntVar: ...


class Rule(ABC):
    order: int = 100
    enabled: bool = True
    name: str = "Rule"

    def __init__(self, model: BuildCtxProto) -> None:
        self.model: BuildCtxProto = model

    def _assumption_literal(self, label: str | None) -> cp_model.IntVar | None:
        """Return an assumption literal (or None) honoring ENABLE_UNSAT_CORE."""
        if not label:
            return None
        cfg = getattr(self.model, "cfg", None)
        if cfg and getattr(cfg, "ENABLE_UNSAT_CORE", False):
            return self.model.add_assumption(label)
        return None

    def _guard(self, constraint: cp_model.Constraint, label: str | None) -> None:
        """Attach readable UNSAT guards without duplicating constraints."""
        lit = self._assumption_literal(label)
        if lit is not None:
            constraint.OnlyEnforceIf(lit)

    def declare_vars(self) -> None:
        return

    def add_hard(self) -> None:
        return

    def add_soft(self) -> None:
        return

    def contribute_objective(self) -> list[cp_model.LinearExpr]:
        return []

    # NEW: generic reporting descriptors (pure data; optional)
    def report_descriptors(self) -> list[dict[str, Any]]:
        """Return zero or more JSON-serializable descriptors that a reporter can use.
        Default: [] (rule has nothing to report)."""
        return []
