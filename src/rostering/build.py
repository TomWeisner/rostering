# src/rostering/build.py
from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, Tuple, cast

from ortools.sat.python import cp_model

from rostering.config import Config
from rostering.data import InputData
from rostering.rules.base import RosterModel
from rostering.rules.objective import ObjectiveBuilder
from rostering.rules.registry import RULE_REGISTRY

if TYPE_CHECKING:
    # Only imported for typing to avoid runtime cycles
    from rostering.rules.base import Rule

# Type aliases for readability
ED = Tuple[int, int]  # (employee, day)
EDH = Tuple[int, int, int]  # (employee, day, hour)


class BuildContext:
    """Holds shared state while building the model (used by rules and solver)."""

    def __init__(self, cfg: Config, data: InputData) -> None:
        self.cfg: Config = cfg
        self.data: InputData = data
        self.m: cp_model.CpModel = cp_model.CpModel()

        # UNSAT-core label map: literal index -> human-friendly label
        self.ASSUMP_LABEL: dict[int, str] = {}

        # Decision/aux placeholders the rules will populate
        self.y: dict[ED, cp_model.IntVar] = {}  # optional shift on day d
        self.S: dict[ED, cp_model.IntVar] = {}  # start hour (0..23)
        self.L: dict[ED, cp_model.IntVar] = {}  # length (MIN..MAX)
        self.x: dict[EDH, cp_model.IntVar] = {}  # worked at hour h
        self.z: dict[ED, cp_model.IntVar] = {}  # worked any hour that day
        self.runlen: dict[ED, cp_model.IntVar] = {}  # running day-count

        # lists of realized hour bits used for min-shift-length constraints
        self.w_cur_list: dict[ED, list[cp_model.IntVar]] = {}
        self.spill_from_day: dict[ED, list[cp_model.IntVar]] = {}

        # Objective accumulator
        self._objective: ObjectiveBuilder = ObjectiveBuilder()

        # Concrete rule instances (filled during build)
        self._rules: list["Rule"] = []

    # ----- helper exposed to rules -----
    def add_assumption(self, label: str) -> cp_model.IntVar:
        """Create an assumption literal with a readable label for UNSAT cores."""
        a = self.m.NewBoolVar(f"a_{len(self.ASSUMP_LABEL)//2}")
        self.ASSUMP_LABEL[a.Index()] = label
        self.ASSUMP_LABEL[a.Not().Index()] = label + " (neg)"
        self.m.AddAssumption(a)
        return a

    def core_labels(self, core: Sequence[int]) -> list[str]:
        """Translate literal indices from the solver into readable labels."""
        return [self.ASSUMP_LABEL.get(k, f"lit#{k}") for k in core]


def build_model(cfg: Config, data: InputData) -> BuildContext:
    """
    Build the CP-SAT model by running each registered Rule through the 4 phases:
      1) declare_vars  2) add_hard  3) add_soft  4) contribute_objective
    Then attach the final objective and run sanity checks.
    """
    ctx = BuildContext(cfg, data)

    # Build sequence from registry
    ctx._rules = RULE_REGISTRY.build_sequence(cast(RosterModel, ctx))

    # Phase 1: variables
    for r in ctx._rules:
        r.declare_vars()

    # Phase 2: hard constraints
    for r in ctx._rules:
        r.add_hard()

    # Phase 3: soft constraints (aux variables etc.)
    for r in ctx._rules:
        r.add_soft()

    # Phase 4: objective terms
    for r in ctx._rules:
        ctx._objective.extend(r.contribute_objective())

    # Finalize objective
    ctx.m.Minimize(ctx._objective.linear_expr())

    # ---- sanity checks (fail fast with clear messages) ----
    expected_x = cfg.N * cfg.DAYS * cfg.HOURS
    if len(ctx.x) != expected_x:
        raise RuntimeError(
            f"[build sanity] x has {len(ctx.x)} keys; expected {expected_x} (N*DAYS*HOURS). "
            "Ensure VariablesRule is registered/enabled and its loops cover all (e,d,h)."
        )
    if not ctx.y or not ctx.S or not ctx.L:
        raise RuntimeError(
            "[build sanity] interval vars missing (y/S/L). VariablesRule likely didn’t run."
        )
    for sent in [(0, 0, 0), (cfg.N - 1, cfg.DAYS - 1, cfg.HOURS - 1)]:
        if sent not in ctx.x:
            raise RuntimeError(
                f"[build sanity] Missing x{sent}; a rule may have overwritten or under-filled x."
            )

    return ctx
