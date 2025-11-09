from __future__ import annotations

from rostering.rules.fairness import FairnessRule
from rostering.rules.registry import default_rule_specs, normalize_rule_specs


def test_normalize_rule_specs_accepts_classes():
    specs = normalize_rule_specs([FairnessRule])
    assert len(specs) == 1
    assert specs[0].cls is FairnessRule


def test_default_rule_specs_returns_fresh_instances():
    first = default_rule_specs()
    second = default_rule_specs()
    assert first[0].cls is second[0].cls
    first[0].settings["demo"] = "x"
    assert "demo" not in second[0].settings
