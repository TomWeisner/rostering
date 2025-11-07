from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotRequirement:
    """Per (day, hour) requirement summarised as max per-slot people and per-skill minima."""

    required_people_for_slot: int  # max_s SKILL_MIN[d][h][s]
    per_skill_minima: dict[str, int]


@dataclass(frozen=True)
class CoverageMetrics:
    """Key coverage metrics summarising assigned vs demanded person-hours."""

    skill_demand_hours: int
    people_hour_lower_bound: int
    assigned_people_hours: int
    assignment_hours_on_demanded_slots: int
    assignment_hours_in_zero_demand_slots: int
    covered_skills: int
    unmatched_assignments_on_demand: int


@dataclass(frozen=True)
class SlotGap:
    """Gap record for a single (day, hour)."""

    day: int
    hour: int
    required_people_for_slot: int
    assigned_people: int
    available_people_upper_bound: int
    deficit: int  # max(required - assigned, 0)
    unattainable: bool  # required_people_for_slot > available_people_upper_bound
