from __future__ import annotations

from typing import Sequence, Tuple, Type

from rostering.rules.availability import AvailabilityRule
from rostering.rules.base import Rule, RuleSpec
from rostering.rules.consecutive_days import ConsecutiveDaysRule
from rostering.rules.coverage import CoverageRule
from rostering.rules.decision_variables import VariablesRule
from rostering.rules.fairness import FairnessRule
from rostering.rules.min_length_shift import MinShiftLengthRule
from rostering.rules.rest import RestRule
from rostering.rules.shift_interval import ShiftIntervalRule
from rostering.rules.weekly_cap import WeeklyCapRule

RuleTemplate = Tuple[Type[Rule], int, dict[str, float]]

VARIABLES_RULE_TEMPLATE: RuleTemplate = (VariablesRule, 0, {})
AVAILABILITY_RULE_TEMPLATE: RuleTemplate = (AvailabilityRule, 10, {})
SHIFT_INTERVAL_RULE_TEMPLATE: RuleTemplate = (ShiftIntervalRule, 20, {})
MIN_SHIFT_LENGTH_RULE_TEMPLATE: RuleTemplate = (MinShiftLengthRule, 40, {})
REST_RULE_TEMPLATE: RuleTemplate = (RestRule, 50, {})
COVERAGE_RULE_TEMPLATE: RuleTemplate = (CoverageRule, 60, {})
WEEKLY_CAP_RULE_TEMPLATE: RuleTemplate = (WeeklyCapRule, 70, {})
CONSECUTIVE_DAYS_RULE_TEMPLATE: RuleTemplate = (
    ConsecutiveDaysRule,
    80,
    {
        "consec_days_before_penality": 5,
        "base": 2.0,
        "scaler": 1.0,
        "scale_int": 1000.0,
        "max_gap": 8,
    },
)
FAIRNESS_RULE_TEMPLATE: RuleTemplate = (
    FairnessRule,
    90,
    {
        "base": 1.4,
        "scale": 1.0,
        "max_deviation_hours": 7,
        "band_shortfall_base": 1.25,
        "band_shortfall_scale": 2.5,
        "band_shortfall_max_gap": 4,
        "band_shortfall_threshold": 2,
    },
)
_DEFAULT_RULE_TEMPLATES: list[RuleTemplate] = [
    VARIABLES_RULE_TEMPLATE,
    AVAILABILITY_RULE_TEMPLATE,
    SHIFT_INTERVAL_RULE_TEMPLATE,
    MIN_SHIFT_LENGTH_RULE_TEMPLATE,
    REST_RULE_TEMPLATE,
    COVERAGE_RULE_TEMPLATE,
    WEEKLY_CAP_RULE_TEMPLATE,
    CONSECUTIVE_DAYS_RULE_TEMPLATE,
    FAIRNESS_RULE_TEMPLATE,
]


def default_rule_specs() -> list[RuleSpec]:
    """Return fresh copies of the default rule specifications."""
    specs: list[RuleSpec] = []
    print("USING DEFAULT RULES")
    for cls, order, settings in _DEFAULT_RULE_TEMPLATES:
        specs.append(RuleSpec(cls=cls, order=order, settings=dict(settings)))
    return specs


def normalize_rule_specs(
    rules: Sequence[RuleSpec | Type[Rule]] | None,
) -> list[RuleSpec]:
    """Turn user-provided rules into RuleSpec objects."""
    if rules is None:
        return default_rule_specs()

    normalized: list[RuleSpec] = []
    for item in rules:
        if isinstance(item, RuleSpec):
            normalized.append(item)
        elif isinstance(item, type) and issubclass(item, Rule):
            normalized.append(RuleSpec(cls=item))
        else:
            raise TypeError(
                "Rules must be RuleSpec instances or Rule subclasses; "
                f"got {type(item)!r}"
            )
    return normalized
