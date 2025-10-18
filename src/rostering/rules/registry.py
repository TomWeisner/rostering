from __future__ import annotations

from typing import TYPE_CHECKING, Type

from .base import Rule

if TYPE_CHECKING:
    from rostering.model import RosterModel

from rostering.rules.availability import AvailabilityRule
from rostering.rules.coverage_minima import CoverageAndMinimaRule
from rostering.rules.decision_variables import VariablesRule
from rostering.rules.fairness import FairnessRule
from rostering.rules.interval_link import IntervalLinkRule
from rostering.rules.min_length_shift import MinRealizedLengthRule
from rostering.rules.rest import RestRule
from rostering.rules.run_penalty import RunPenaltyRule
from rostering.rules.weekly_cap import WeeklyCapRule


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: list[Type[Rule]] = []

    def register(self, rule_cls: Type[Rule]) -> Type[Rule]:
        """Register a Rule subclass. Usable as a decorator."""
        self._rules.append(rule_cls)
        return rule_cls

    def build_sequence(self, model: RosterModel) -> list[Rule]:
        """
        Instantiate registered Rule classes, keep only enabled ones,
        and return them ordered by .order.
        """
        instances: list[Rule] = [rule_cls(model) for rule_cls in self._rules]
        enabled = [r for r in instances if getattr(r, "enabled", True)]
        enabled.sort(key=lambda r: r.order)
        print(f"N={model.cfg.N} rules enabled: {len(enabled)}")
        return enabled


# Global registry
RULE_REGISTRY = RuleRegistry()
RULE_REGISTRY.register(VariablesRule)
RULE_REGISTRY.register(AvailabilityRule)
RULE_REGISTRY.register(IntervalLinkRule)
RULE_REGISTRY.register(MinRealizedLengthRule)
RULE_REGISTRY.register(RestRule)
RULE_REGISTRY.register(CoverageAndMinimaRule)
RULE_REGISTRY.register(WeeklyCapRule)
RULE_REGISTRY.register(RunPenaltyRule)
RULE_REGISTRY.register(FairnessRule)
