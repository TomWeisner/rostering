# rostering/model.py
from __future__ import annotations

from typing import Sequence, Type

import pandas as pd

from rostering.build import build_model
from rostering.config import Config
from rostering.extract import (
    compute_agg_run,
    extract_employee_totals,
    extract_hourly,
    extract_shifts,
)
from rostering.input_data import InputData
from rostering.precheck import precheck_availability
from rostering.result_types import SolveResult
from rostering.rules.base import Rule, RuleSpec
from rostering.solver import solve_model


class RosterModel:
    """
    Thin orchestrator around:
      - precheck_availability()
      - build_model()      -> returns BuildContext with model + variables
      - solve_model()      -> runs CP-SAT
      - extraction helpers -> pandas DataFrames + summary stats
    """

    def __init__(
        self,
        cfg: Config,
        data: InputData,
        rules: Sequence[RuleSpec | Type[Rule]] | None = None,
    ):
        self.cfg = cfg
        self.data = data
        self._ctx = None  # populated by build()
        self._model_stats: str | None = None
        self._rule_specs = rules

    # ---------- Precheck ----------
    def precheck(self):
        return precheck_availability(self.cfg, self.data)

    # ---------- Build ----------
    def build(self):
        """
        Build the CP-SAT model by running each registered Rule through the 4 phases:
          1) declare_vars  2) add_hard  3) add_soft  4) contribute_objective
        Then attach the final objective and run sanity checks.
        """
        self._ctx = build_model(self.cfg, self.data, rules=self._rule_specs)
        if hasattr(self._ctx, "m"):
            try:
                self._model_stats = self._ctx.m.ModelStats()
            except AttributeError:
                self._model_stats = None

    # ---------- Solve ----------
    def solve(self, progress_cb=None) -> SolveResult:
        """
        Solve the CP-SAT model.

        If the model is infeasible, the method will return early with
        unsat_core_groups containing the unsatisfiable core.

        Otherwise, it will return a SolveResult object with the final
        status, objective value, and extracted results as pandas DataFrames
        and summary statistics.

        Parameters:
        progress_cb (callable): a progress callback function for the solver

        Returns:
        SolveResult: a structured object containing the final status, objective
        value, extracted results, and summary statistics
        """
        if self._ctx is None:
            raise RuntimeError("Call build() before solve().")

        print("\nSolving...")
        solver, status_name, unsat_groups = solve_model(
            self._ctx, progress_cb=progress_cb
        )
        solver_stats = solver.ResponseStats()

        progress_history = None
        if progress_cb is not None:
            if hasattr(progress_cb, "solution_history") and callable(
                getattr(progress_cb, "solution_history")
            ):
                progress_history = progress_cb.solution_history()
            else:
                progress_history = getattr(progress_cb, "history", None)

        # Infeasible? return early with core info
        if status_name == "INFEASIBLE":
            return SolveResult(
                status_name=status_name,
                objective_value=None,
                df_sched=pd.DataFrame(),
                df_shifts=pd.DataFrame(),
                df_emp=pd.DataFrame(),
                avg_run=0.0,
                max_run=0.0,
                unsat_core_groups=unsat_groups,
                progress_history=progress_history,
                solver_stats=solver_stats,
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
                unsat_core_groups=unsat_groups,
                progress_history=progress_history,
                solver_stats=solver_stats,
            )

        # Extract results
        df_sched = extract_hourly(self._ctx, solver)
        df_shifts = extract_shifts(self._ctx, solver)
        df_emp = extract_employee_totals(self._ctx, solver)
        avg_run = compute_agg_run(self._ctx, solver, agg="mean")
        max_run = compute_agg_run(self._ctx, solver, agg="max")
        obj_val = solver.ObjectiveValue()

        return SolveResult(
            status_name=status_name,
            objective_value=obj_val,
            df_sched=df_sched,
            df_shifts=df_shifts,
            df_emp=df_emp,
            avg_run=avg_run,
            max_run=max_run,
            unsat_core_groups={},
            progress_history=progress_history,
            solver_stats=solver_stats,
        )

    def get_report_descriptors(self) -> list[dict]:
        if self._ctx is None:
            raise RuntimeError("Call build() before get_report_descriptors().")
        return self._ctx.report_descriptors()

    def model_stats(self) -> str | None:
        return self._model_stats
