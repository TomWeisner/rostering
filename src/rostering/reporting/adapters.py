from __future__ import annotations

from typing import Any, Optional, Protocol, cast

import pandas as pd


class ResultAdapter(Protocol):
    """Minimal interface the Reporter needs to work with any model/solution object."""

    def status_name(self, res: Any) -> str: ...
    def objective_value(self, res: Any) -> Optional[float]: ...
    def avg_consecutive_workday_run(self, res: Any) -> Optional[float]: ...
    def max_consecutive_workday_run(self, res: Any) -> Optional[int]: ...

    def df_emp(self, res: Any) -> pd.DataFrame: ...
    def df_sched(self, res: Any) -> pd.DataFrame: ...
    def df_shifts(self, res: Any) -> pd.DataFrame: ...


class PandasResultAdapter:
    """Default adapter for the shipped SolveResult dataclass."""

    def status_name(self, res: Any) -> str:
        return getattr(res, "status_name", "UNKNOWN")

    def objective_value(self, res: Any) -> Optional[float]:
        return cast(Optional[float], getattr(res, "objective_value", None))

    def avg_consecutive_workday_run(self, res: Any) -> Optional[float]:
        return cast(Optional[float], getattr(res, "avg_run", None))

    def max_consecutive_workday_run(self, res: Any) -> Optional[int]:
        return cast(Optional[int], getattr(res, "max_run", None))

    def df_emp(self, res: Any) -> pd.DataFrame:
        df = cast(pd.DataFrame, getattr(res, "df_emp", pd.DataFrame()))
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    def df_sched(self, res: Any) -> pd.DataFrame:
        df = cast(pd.DataFrame, getattr(res, "df_sched", pd.DataFrame()))
        if df.empty:
            return df
        cols = {str(c).lower(): c for c in df.columns}
        req = ("employee_id", "day", "hour")
        if all(k in cols for k in req):
            out = df[[cols["employee_id"], cols["day"], cols["hour"]]].copy()
            out.columns = ["employee_id", "day", "hour"]
            return out.astype({"employee_id": int, "day": int, "hour": int})
        return pd.DataFrame()

    def df_shifts(self, res: Any) -> pd.DataFrame:
        df = cast(pd.DataFrame, getattr(res, "df_shifts", pd.DataFrame()))
        if df.empty:
            return df

        sc = {str(c).lower(): c for c in df.columns}

        emp_col = next(
            (
                sc[c]
                for c in ("employee_id", "emp_id", "e", "worker_id", "staff_id")
                if c in sc
            ),
            None,
        )
        start_day_col = next(
            (sc[c] for c in ("start_day", "day", "day_index", "day_idx") if c in sc),
            None,
        )
        start_hour_col = next(
            (sc[c] for c in ("start_hour", "hour", "h") if c in sc), None
        )
        length_col = next(
            (
                sc[c]
                for c in (
                    "length_h",
                    "model_length_h",
                    "dur_h",
                    "duration_h",
                    "duration",
                )
                if c in sc
            ),
            None,
        )

        if not start_day_col:
            date_col = next(
                (sc[c] for c in ("start_date", "date", "day_date") if c in sc), None
            )
            if date_col:
                base = pd.to_datetime(df[date_col]).min()
                df = df.assign(start_day=(pd.to_datetime(df[date_col]) - base).dt.days)
                start_day_col = "start_day"

        if not all([emp_col, start_day_col, start_hour_col, length_col]):
            return pd.DataFrame()

        out = df[[emp_col, start_day_col, start_hour_col, length_col]].copy()
        out.columns = ["employee_id", "start_day", "start_hour", "length_h"]
        out["employee_id"] = pd.to_numeric(out["employee_id"], errors="coerce").astype(
            "Int64"
        )
        out["start_day"] = pd.to_numeric(out["start_day"], errors="coerce").astype(
            "Int64"
        )
        out["start_hour"] = pd.to_numeric(out["start_hour"], errors="coerce").astype(
            "Int64"
        )
        out["length_h"] = pd.to_numeric(out["length_h"], errors="coerce").astype(
            "Int64"
        )
        out = out.dropna().astype(int)
        return out
