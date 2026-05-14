"""
init_data: CSV path or DataFrame with SETTLEMENTDATE + TOTALDEMAND + RRP.
reduction_interval: (start_hour, end_hour) in [0, 24], end exclusive, wraps midnight if start > end, or None.
free_interval: same shape; hours shared with reduction_interval are excluded from reduction.
peak_reduction: percent demand reduction during reduction_interval.
rebound_percentage: percent demand uplift during free_interval.
save: write the modelled DataFrame to data/modelled/.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "modelled"

Interval = Optional[Tuple[int, int]]


def _interval_hours(interval: Interval) -> set[int]:
    if interval is None:
        return set()
    a, b = interval
    if not (0 <= a <= 24 and 0 <= b <= 24):
        raise ValueError(f"Interval hours must be in [0, 24]: {interval}")
    if a == b:
        return set()
    if a < b:
        return set(range(a, b))
    return set(range(a, 24)) | set(range(0, b))


def model(
    init_data: Union[str, Path, pd.DataFrame],
    reduction_interval: Interval,
    free_interval: Interval,
    peak_reduction: float,
    rebound_percentage: float,
    output_name: Optional[str] = None,
    save: bool = True,
) -> Tuple[pd.DataFrame, Optional[Path]]:

    if isinstance(init_data, (str, Path)):
        df = pd.read_csv(init_data, parse_dates=["SETTLEMENTDATE"])
    else:
        df = init_data.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["SETTLEMENTDATE"]):
            df["SETTLEMENTDATE"] = pd.to_datetime(df["SETTLEMENTDATE"])

    red_hours = _interval_hours(reduction_interval)
    free_hours = _interval_hours(free_interval)
    red_hours = red_hours - free_hours

    df = df.sort_values("SETTLEMENTDATE").reset_index(drop=True)
    hours = df["SETTLEMENTDATE"].dt.hour

    df["ORIGINAL_DEMAND"] = df["TOTALDEMAND"].astype(float)
    df["MODELLED_DEMAND"] = df["ORIGINAL_DEMAND"].copy()

    if red_hours:
        df.loc[hours.isin(red_hours), "MODELLED_DEMAND"] *= 1.0 - peak_reduction / 100.0
    if free_hours:
        df.loc[hours.isin(free_hours), "MODELLED_DEMAND"] *= 1.0 + rebound_percentage / 100.0

    out_path: Optional[Path] = None
    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        if output_name is None:
            first = df["SETTLEMENTDATE"].iloc[0]
            region = (df["REGION"].iloc[0] if "REGION" in df.columns else "region").lower()
            output_name = f"modelled_{region}_{first:%Y%m}.csv"
        out_path = OUT_DIR / output_name
        df.to_csv(out_path, index=False)

    return df, out_path


if __name__ == "__main__":
    sample = ROOT / "data" / "processed" / "average" / "vic1_2025_summer_weekday.csv"
    out_df, out_path = model(
        init_data=sample,
        reduction_interval=(17, 21),
        free_interval=(11, 15),
        peak_reduction=15.0,
        rebound_percentage=8.0,
        output_name="modelled_vic1_2025_summer_weekday.csv",
    )
    print(f"Saved {out_path}")
    print(out_df[["SETTLEMENTDATE", "ORIGINAL_DEMAND", "MODELLED_DEMAND"]].head())
