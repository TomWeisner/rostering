# src/rostering/rules/objective.py
from __future__ import annotations

from typing import Iterable

from ortools.sat.python import cp_model


class ObjectiveBuilder:
    """
    Small helper that lets rules contribute penalty terms and emits a single LinearExpr.

    Usage:
        weight = 10
        obj = ObjectiveBuilder()
        obj.add(weight * bool_var)
        model.Minimize(obj.linear_expr())
    """

    __slots__ = ("terms",)

    def __init__(self) -> None:
        self.terms: list[cp_model.LinearExpr] = []

    def add(self, term: cp_model.LinearExpr) -> "ObjectiveBuilder":
        """Add a single linear expression term (chainable)."""
        self.terms.append(term)
        return self

    def extend(self, terms: Iterable[cp_model.LinearExpr]) -> "ObjectiveBuilder":
        """Add multiple terms (chainable)."""
        self.terms.extend(terms)
        return self

    def linear_expr(self) -> cp_model.LinearExpr:
        """
        Return a LinearExpr that is the sum of all terms.
        Ensure the return type is cp_model.LinearExpr even when empty.
        """
        if not self.terms:
            # Sum([]) returns an int; wrap to keep the type as LinearExpr.
            return cp_model.LinearExpr.Sum([0])
        return cp_model.LinearExpr.Sum(self.terms)
