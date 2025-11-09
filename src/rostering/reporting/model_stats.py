from __future__ import annotations

import re


def _parse_number(value: str) -> int:
    """Convert strings like "90'774" or "1,200" into ints."""
    clean = value.replace("'", "").replace(",", "").strip()
    return int(clean)


def _format_numeric_string(value: str | None) -> str | None:
    """Format numeric strings with thousands separators when possible."""
    if value is None:
        return None
    try:
        num = float(value.replace(",", ""))
    except ValueError:
        return value
    if abs(num - round(num)) < 1e-6:
        return f"{int(round(num)):,}"
    formatted = f"{num:,.3f}".rstrip("0").rstrip(".")
    return formatted


def format_model_stats(stats: str | None) -> str | None:
    """Extract key metrics from CpModel.ModelStats()."""
    if not stats:
        return None

    total_vars = bools = ints = None
    constraint_total = 0
    for raw_line in stats.splitlines():
        line = raw_line.strip()
        if line.startswith("#Variables:"):
            m_total = re.search(r"#Variables:\s*([\d,' ]+)", line)
            m_bools = re.search(r"#bools:\s*([\d,' ]+)", line)
            m_ints = re.search(r"#ints:\s*([\d,' ]+)", line)
            if m_total:
                total_vars = _parse_number(m_total.group(1))
            if m_bools:
                bools = _parse_number(m_bools.group(1))
            if m_ints:
                ints = _parse_number(m_ints.group(1))
        elif line.startswith("#k"):
            try:
                count = _parse_number(line.split(":", 1)[1].split()[0])
                constraint_total += count
            except (IndexError, ValueError):
                continue

    if total_vars is None:
        return None

    var_line = f"  Variables: total={total_vars:,}"
    details: list[str] = []
    if bools is not None:
        details.append(f"booleans={bools:,}")
    if ints is not None:
        details.append(f"integers={ints:,}")
    if details:
        var_line += " (" + ", ".join(details) + ")"

    parts = [var_line]
    if constraint_total:
        parts.append(
            f"  Approximated constraints (linear/max/element): {constraint_total:,}"
        )
    return "\n".join(parts)


def format_solver_stats(stats: str | None) -> str | None:
    """Extract the most helpful runtime metrics from CpSolver.ResponseStats()."""
    if not stats:
        return None

    lines: dict[str, str] = {}
    for line in stats.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        lines[key.strip().lower()] = val.strip()

    status = lines.get("status")
    if status is None:
        return None

    obj_fmt = _format_numeric_string(lines.get("objective"))
    bound_fmt = _format_numeric_string(lines.get("best_bound"))
    conflicts_fmt = _format_numeric_string(lines.get("conflicts"))
    branches_fmt = _format_numeric_string(lines.get("branches"))
    props_fmt = _format_numeric_string(lines.get("propagations"))
    wall_raw = lines.get("walltime")
    wall_fmt = None
    if wall_raw is not None:
        try:
            wall_fmt = f"{float(wall_raw):,.2f}"
        except ValueError:
            wall_fmt = wall_raw

    summary = [
        f"  Status={status}"
        + (f", objective={obj_fmt}" if obj_fmt is not None else "")
        + (f", best_bound={bound_fmt}" if bound_fmt is not None else "")
    ]
    if conflicts_fmt:
        summary.append(
            "  Conflicts="
            + conflicts_fmt
            + ", branches="
            + (branches_fmt or lines.get("branches") or "n/a")
            + ", propagations="
            + (props_fmt or lines.get("propagations") or "n/a")
        )
    if wall_fmt:
        summary.append(f"  Walltime={wall_fmt}s")
    return "\n".join(summary)
