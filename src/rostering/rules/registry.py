from __future__ import annotations

from typing import Type

from rostering.rules.availability import AvailabilityRule
from rostering.rules.base import BuildCtxProto, Rule
from rostering.rules.coverage import CoverageRule
from rostering.rules.decision_variables import VariablesRule
from rostering.rules.fairness import FairnessRule
from rostering.rules.interval_link import IntervalLinkRule
from rostering.rules.min_length_shift import MinRealizedLengthRule
from rostering.rules.rest import RestRule
from rostering.rules.run_penalty import RunPenaltyRule
from rostering.rules.weekly_cap import WeeklyCapRule


class RuleRegistry:
    def __init__(self) -> None:
        # Store rule CLASSES, not instances
        self._rules: list[Type[Rule]] = []

    def register(self, rule_cls: Type[Rule]) -> Type[Rule]:
        self._rules.append(rule_cls)
        return rule_cls

    def build_sequence(self, ctx: BuildCtxProto) -> list[Rule]:
        """
        Instantiate registered Rule classes, keep only enabled ones,
        and return them ordered by .order.
        """
        instances: list[Rule] = [rule_cls(ctx) for rule_cls in self._rules]
        enabled = [r for r in instances if getattr(r, "enabled", True)]
        enabled.sort(key=lambda r: r.order)
        print(f"\nN={ctx.cfg.N:,} employees to be assigned shifts")
        print(
            f"D={ctx.cfg.DAYS:,} days to be covered, {ctx.cfg.HOURS:,} hours per day = {ctx.cfg.DAYS*ctx.cfg.HOURS:,} slots"
        )
        print(f"R={len(enabled):,} rules enabled")
        print(f"P={ctx.cfg.NUM_WORKERS:,} parallel computes\n")
        return enabled


# ---- registrations ----
RULE_REGISTRY = RuleRegistry()
RULE_REGISTRY.register(VariablesRule)
RULE_REGISTRY.register(AvailabilityRule)
RULE_REGISTRY.register(IntervalLinkRule)
RULE_REGISTRY.register(MinRealizedLengthRule)
RULE_REGISTRY.register(RestRule)
RULE_REGISTRY.register(CoverageRule)
RULE_REGISTRY.register(WeeklyCapRule)
RULE_REGISTRY.register(RunPenaltyRule)
RULE_REGISTRY.register(FairnessRule)
