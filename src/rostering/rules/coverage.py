# src/rostering/rules/coverage.py
from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Set

from rostering.config import Config
from rostering.data import InputData
from rostering.rules.base import Rule


def _collect_required_skills(C: Config) -> Set[str]:
    """Gather every skill token that appears anywhere in SKILL_MIN / SKILL_MAX."""
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
    employee_index -> bool using Staff.skills (set/list) or dict[str,bool] (True==has).
    """
    staff = list(getattr(D, "staff", []) or [])

    @lru_cache(maxsize=None)
    def _resolver(skill_name: str) -> Callable[[int], bool]:
        def _pred(e: int) -> bool:
            if not (0 <= e < len(staff)):
                return False
            sk = getattr(staff[e], "skills", None)
            if isinstance(sk, dict):
                return bool(sk.get(skill_name, False))
            try:
                return skill_name in set(sk or [])
            except TypeError:
                return bool(
                    getattr(
                        staff[e],
                        f"skill{skill_name}",
                        getattr(staff[e], skill_name, False),
                    )
                )

        return _pred

    return _resolver


class CoverageRule(Rule):
    """
    Enforce hard per-skill coverage:
      a[e,d,h,s] = 1 if employee e covers skill s at (d,h).
      Hard constraints:
        - ∑_e a[e,d,h,s] ≥ SKILL_MIN[d][h][s]   (if provided)
        - ∑_e a[e,d,h,s] ≤ SKILL_MAX[d][h][s]   (if provided)
        - ∑_s a[e,d,h,s] ≤ x[e,d,h]             (each employee covers ≤1 skill per hour)
      Eligibility:
        - a[e,d,h,s] = 0 if employee lacks skill s, hour disallowed by mask, or day is a holiday.
    This implies the people-hour lower bound and prevents “unassigned shifts”
    whenever minima are feasible.
    """

    order = 60
    name = "CoverageMinima"

    def report_descriptors(self) -> list[dict[str, Any]]:
        """Keep the existing descriptor for your reporter."""
        C: Config = self.model.cfg
        D: InputData = self.model.data

        skills = sorted(_collect_required_skills(C))
        resolve = _make_predicate_resolver(D)

        n_emp = int(getattr(C, "N", 0))
        eligible: dict[str, list[int]] = {
            s: [e for e in range(n_emp) if resolve(s)(e)] for s in skills
        }

        skill_min = getattr(C, "SKILL_MIN", None)
        skill_max = getattr(C, "SKILL_MAX", None)

        def get_min(d: int, h: int) -> dict[str, int]:
            return dict(skill_min[d][h]) if skill_min is not None else {}

        def get_max(d: int, h: int) -> dict[str, int]:
            return dict(skill_max[d][h]) if skill_max is not None else {}

        def compute_requirements(d: int, h: int) -> dict[str, Any]:
            return {"min": get_min(d, h), "max": get_max(d, h)}

        return [
            {
                "type": "coverage",
                "name": self.name,
                "skills": skills,
                "eligible": eligible,
                "get_requirements": compute_requirements,
                "DAYS": int(getattr(C, "DAYS", 0)),
                "HOURS": int(getattr(C, "HOURS", 0)),
            }
        ]

    # ---------- NEW: decision vars for coverage ----------
    def declare_vars(self):
        """
        Create a[e,d,h,s] BoolVars only where there is any min/max demand for skill s
        (keeps the model smaller than creating the full dense grid).
        """
        C, m = self.model.cfg, self.model.m
        DAYS, HOURS = int(C.DAYS), int(C.HOURS)

        skill_min = getattr(C, "SKILL_MIN", None) or [
            [{} for _ in range(HOURS)] for _ in range(DAYS)
        ]
        skill_max = getattr(C, "SKILL_MAX", None) or [
            [{} for _ in range(HOURS)] for _ in range(DAYS)
        ]

        self.model.a = {}  # (e,d,h,s) -> BoolVar

        for d in range(DAYS):
            for h in range(HOURS):
                # build the set of skills that matter in this slot (min or max present)
                slot_skills = set(skill_min[d][h].keys()) | set(skill_max[d][h].keys())
                if not slot_skills:
                    continue
                for s in slot_skills:
                    for e in range(int(C.N)):
                        self.model.a[(e, d, h, s)] = m.NewBoolVar(
                            f"a_e{e}_d{d}_h{h}_s{s}"
                        )

    # ---------- NEW: hard constraints ----------
    def add_hard(self):
        C, D, m = self.model.cfg, self.model.data, self.model.m
        DAYS, HOURS = int(C.DAYS), int(C.HOURS)

        # Required data from other rules:
        # - x[(e,d,h)] must exist (hour-work BoolVar)
        x = self.model.x

        # Helpers
        resolve_skill = _make_predicate_resolver(D)
        allowed = getattr(
            D, "allowed", None
        )  # shape [N][HOURS] booleans per employee/hour

        skill_min = getattr(C, "SKILL_MIN", None) or [
            [{} for _ in range(HOURS)] for _ in range(DAYS)
        ]
        skill_max = getattr(C, "SKILL_MAX", None) or [
            [{} for _ in range(HOURS)] for _ in range(DAYS)
        ]

        # 1) Link each skill assignment to being at work that hour
        for (e, d, h, s), var in self.model.a.items():
            m.Add(var <= x[(e, d, h)])

        # 2) Eligibility pruning: a[e,d,h,s] = 0 if employee cannot cover s at (d,h)
        for (e, d, h, s), var in self.model.a.items():
            has_skill = resolve_skill(s)(e)
            hour_ok = bool(allowed[e][h]) if allowed is not None else True
            is_holiday = d in set(getattr(D.staff[e], "holidays", []))
            if not (has_skill and hour_ok and not is_holiday):
                m.Add(var == 0)

        # 3) Hard minima / maxima per skill
        for d in range(DAYS):
            for h in range(HOURS):
                slot_min = skill_min[d][h] or {}
                slot_max = skill_max[d][h] or {}

                # Min: ∑_e a ≥ SKILL_MIN[d][h][s]
                for s, req in slot_min.items():
                    req = int(req)
                    if req > 0:
                        a_e = [
                            self.model.a[(e, d, h, s)]
                            for e in range(int(C.N))
                            if (e, d, h, s) in self.model.a
                        ]
                        if (
                            a_e
                        ):  # if there are no vars, it's infeasible; let solver detect
                            m.Add(sum(a_e) >= req)

                # Max: ∑_e a ≤ SKILL_MAX[d][h][s]
                for s, cap in slot_max.items():
                    cap = int(cap)
                    if cap >= 0:
                        a_e = [
                            self.model.a[(e, d, h, s)]
                            for e in range(int(C.N))
                            if (e, d, h, s) in self.model.a
                        ]
                        if a_e:
                            m.Add(sum(a_e) <= cap)
