# src/rostering/rules/coverage.py
from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Set

from rostering.config import Config
from rostering.data import InputData
from rostering.rules.base import Rule


def _collect_required_skills(C: Config) -> Set[str]:
    """
    Gather every skill token that appears anywhere in SKILL_MIN / SKILL_MAX.
    No special-casing; skills appear only if present in the grids.
    """
    skills: Set[str] = set()

    skill_min = getattr(C, "SKILL_MIN", None)
    if skill_min is not None:
        for row in skill_min:
            for slot in row:
                skills.update(slot.keys())

    skill_max = getattr(C, "SKILL_MAX", None)
    if skill_max is not None:
        for row in skill_max:
            for slot in row:
                skills.update(slot.keys())

    return skills


def _make_predicate_resolver(D: InputData) -> Callable[[str], Callable[[int], bool]]:
    """
    Return a resolver that, for a given skill name, produces a predicate
    employee_index -> bool using Staff.skills (list[str]).
    """
    staff = list(getattr(D, "staff", []) or [])

    @lru_cache(maxsize=None)
    def _resolver(skill_name: str) -> Callable[[int], bool]:
        def _pred(e: int) -> bool:
            return 0 <= e < len(staff) and (
                skill_name in getattr(staff[e], "skills", [])
            )

        return _pred

    return _resolver


class CoverageRule(Rule):
    order = 60
    name = "CoverageMinima"

    def report_descriptors(self) -> list[dict[str, Any]]:
        """
        Expose a generic descriptor the reporter can consume.
        Skills and eligibility are driven purely by Config + Data.
        """
        C: Config = self.model.cfg  # type: ignore[assignment]
        D: InputData = self.model.data  # type: ignore[assignment]

        # Skills come strictly from the configured grids
        skills = sorted(_collect_required_skills(C))
        resolve = _make_predicate_resolver(D)

        # Eligible employees per skill
        n_emp = int(getattr(C, "N", 0))
        eligible: dict[str, list[int]] = {
            s: [e for e in range(n_emp) if resolve(s)(e)] for s in skills
        }

        # Narrow grids once and provide safe accessors
        skill_min = getattr(C, "SKILL_MIN", None)
        skill_max = getattr(C, "SKILL_MAX", None)

        def get_min(d: int, h: int) -> dict[str, int]:
            if skill_min is not None:
                return dict(skill_min[d][h])
            return {}

        def get_max(d: int, h: int) -> dict[str, int]:
            if skill_max is not None:
                return dict(skill_max[d][h])
            return {}

        def compute_requirements(d: int, h: int) -> dict[str, Any]:
            return {"min": get_min(d, h), "max": get_max(d, h)}

        return [
            {
                "type": "coverage",
                "name": self.name,
                "skills": skills,
                "eligible": eligible,  # {skill: [employee_ids]}
                "get_requirements": compute_requirements,
                "DAYS": int(getattr(C, "DAYS", 0)),
                "HOURS": int(getattr(C, "HOURS", 0)),
            }
        ]
