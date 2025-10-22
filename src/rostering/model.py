# rostering/model.py
from __future__ import annotations

import pandas as pd

from rostering.build import build_model
from rostering.config import Config
from rostering.data import InputData
from rostering.extract import (
    compute_avg_run,
    extract_employee_totals,
    extract_hourly,
    extract_shifts,
)
from rostering.precheck import precheck_availability
from rostering.result_types import SolveResult
from rostering.solver import solve_model


class RosterModel:
    """
    Thin orchestrator around:
      - precheck_availability()
      - build_model()      -> returns BuildContext with model + variables
      - solve_model()      -> runs CP-SAT
      - extraction helpers -> pandas DataFrames + summary stats
    """

    def __init__(self, cfg: Config, data: InputData):
        self.cfg = cfg
        self.data = data
        self._ctx = None  # populated by build()

    # ---------- Precheck ----------
    def precheck(self):
        return precheck_availability(self.cfg, self.data)

    # ---------- Build ----------
    def build(self):
        self._ctx = build_model(self.cfg, self.data)

    # ---------- Solve ----------
    def solve(self, progress_cb=None) -> SolveResult:
        if self._ctx is None:
            raise RuntimeError("Call build() before solve().")

        print("Solving...")
        solver, status_name, unsat_groups = solve_model(
            self._ctx, progress_cb=progress_cb
        )

        # Infeasible? return early with core info
        if status_name == "INFEASIBLE":
            return SolveResult(
                status_name=status_name,
                objective_value=None,
                df_sched=pd.DataFrame(),
                df_shifts=pd.DataFrame(),
                df_emp=pd.DataFrame(),
                avg_run=0.0,
                unsat_core_groups=unsat_groups,
            )

        # Non-final status (e.g., UNKNOWN) — still return what we can
        if status_name not in ("OPTIMAL", "FEASIBLE"):
            return SolveResult(
                status_name,
                None,
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                0.0,
                {},
            )

        # Extract results
        df_sched = extract_hourly(self._ctx, solver)
        df_shifts = extract_shifts(self._ctx, solver)
        df_emp = extract_employee_totals(self._ctx, solver)
        avg_run = compute_avg_run(self._ctx, solver)
        obj_val = solver.ObjectiveValue()

        return SolveResult(
            status_name=status_name,
            objective_value=obj_val,
            df_sched=df_sched,
            df_shifts=df_shifts,
            df_emp=df_emp,
            avg_run=avg_run,
            unsat_core_groups={},
        )

    def get_report_descriptors(self) -> list[dict]:
        if self._ctx is None:
            raise RuntimeError("Call build() before get_report_descriptors().")
        return self._ctx.report_descriptors()
