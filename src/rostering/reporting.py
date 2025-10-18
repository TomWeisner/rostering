def print_precheck(cfg, cap, dem, ok_cap, buckets):
    print(
        f"Pre-check: cap={cap} (N*MAX_SHIFT_H) vs dem={dem} (COVER*HOURS) | OK={ok_cap}"
    )
    names = (
        "Allowed staff < COVER",
        "Senior below min",
        "Skill A below min",
        "Skill B below min",
    )
    for name, lst in zip(names, buckets):
        if not lst:
            continue
        examples = ", ".join(
            f"d={d},h={h:02d} (have {v})"
            for d, h, v in lst[: cfg.PRINT_PRECHECK_EXAMPLES]
        )
        print(f"- {name}: {len(lst)} hours (e.g. {examples})")


def print_unsat_core(groups):
    if not groups:
        print("No UNSAT core available (search or build does not support it).")
        return
    print("Unsat core (grouped):")
    for key, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        sample = ", ".join(sorted(items)[:5])
        more = f" (+{len(items)-5} more)" if len(items) > 5 else ""
        print(f"- {key}: {len(items)}; e.g. {sample}{more}")


def print_summary(cfg, res):
    required = int(cfg.DAYS * cfg.HOURS * cfg.COVER)
    print(f"\nSummary: assignments={len(res.df_sched)} | required={required}")
    if cfg.PRINT_POSTSUM_HEAD > 0 and not res.df_sched.empty:
        print(res.df_sched.head(cfg.PRINT_POSTSUM_HEAD).to_string(index=False))
    print(f"\nAvg run length over worked days: {res.avg_run:.2f}")
    if res.objective_value is not None:
        print(f"Objective value (overall penalty): {res.objective_value:.0f}")


def print_per_employee_cap(cfg, df_emp):
    print("\nPer-employee hours (top 12):")
    print(df_emp.head(12).to_string(index=False))
    if cfg.WEEKLY_MAX_HOURS is not None:
        over_cap = df_emp[df_emp["hours"] > cfg.WEEKLY_MAX_HOURS]
        if not over_cap.empty:
            print(f"\n⚠️ Employees over cap {cfg.WEEKLY_MAX_HOURS}h:")
            print(over_cap.to_string(index=False))
        else:
            print(f"\nAll employees within weekly cap ({cfg.WEEKLY_MAX_HOURS}h).")


def print_shift_aware(cfg, res, staff, inspect_ids):
    def fmt_h(h):
        return f"{int(h):02d}:00"

    if not inspect_ids:
        return
    print("\nDetailed shifts for selected employees (interval view):")
    df = res.df_shifts
    for ee in inspect_ids:
        if ee < 0 or ee >= cfg.N:
            print(f"- id {ee}: (invalid id)")
            continue
        s = staff[ee]
        df_e = df[df["employee_id"] == ee]
        print(
            f"\nEmployee id={ee} | {s.name} | band={s.band} | A={int(s.skillA)} | B={int(s.skillB)} | night={int(getattr(s,'is_night_worker',0))}"
        )
        if df_e.empty:
            print("  (no shifts assigned)")
            continue
        total_realized = 0
        for _, row in df_e.sort_values(["start_date", "start_hour"]).iterrows():
            start_date = row["start_date"]
            end_date = row["end_date"]
            sh = int(row["start_hour"])
            eh = int(row["end_hour"])
            Lh = int(row["model_length_h"])
            rh = int(row["realized_h"])
            total_realized += rh
            if start_date == end_date:
                print(
                    f"  {start_date}  {fmt_h(sh)} → {fmt_h(eh)} (model L={Lh}h, realized={rh}h)"
                )
            else:
                print(
                    f"  {start_date}  {fmt_h(sh)} → {end_date} {fmt_h(eh)} (model L={Lh}h, realized={rh}h)"
                )
        print(f"  Total realized hours across all shifts: {total_realized}")
