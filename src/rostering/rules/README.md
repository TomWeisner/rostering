# Rules subsystem

This package defines every CP-SAT rule (a small, composable component that declares variables, adds constraints, and contributes penalties). Rules are orchestrated via `RuleSpec` objects and assembled in `registry.py`.

| Module | Purpose |
| --- | --- |
| `base.py` | Defines `Rule`, the hooks (`declare_vars`, `add_hard`, `add_soft`, `contribute_objective`) and `RuleSpec`. All rule implementations inherit from here. |
| `registry.py` | Lists the default rule templates (class + order + settings) used by `run_solver`. Projects can supply custom specs to override the defaults. |
| `decision_variables.py` | Declares the core assignment variables (`x/y/z`, start/end times, interval lengths) shared by downstream rules. Must run first! |
| `availability.py` | Enforces allowed-hour masks (weekend/holiday exclusions, night-worker limits, etc.). |
| `shift_interval.py` | Builds start/length relationships for each employee/day so later rules can reason about contiguous shifts. |
| `min_length_shift.py` | Hard rule that forces every active shift to be at least `MIN_SHIFT_HOURS`. Also documents why no explicit max-shift rule is needed (upper bounds sit on interval vars). |
| `rest.py` | Enforces rest windows between shifts and bounds on night→day transitions. |
| `coverage.py` | Meets per-hour/per-skill minima (uses the skill grids ensured by `Config.ensure_skill_grids`). |
| `weekly_cap.py` | Caps per-employee total hours when `WEEKLY_MAX_HOURS` is set. |
| `consecutive_days.py` | Tracks consecutive-day runs and applies soft penalties or hard cutoffs. Uses cached helper tables to keep the model small. |
| `fairness.py` | Balances total hours via exponential penalties, with an optional band-shortfall overlay; now also hosts the old “band shortfall” logic. |

Adding a new rule:

1. Subclass `Rule` in a new module; follow the declare/add/contribute lifecycle.
2. Keep helper math in `helpers.py` when the data can be reused by multiple rules.
3. Register the rule in `registry.py` (or supply your own `RuleSpec` list to `run_solver`) so it participates in the build order. |
