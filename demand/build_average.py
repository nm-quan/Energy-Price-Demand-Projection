"""
summary: average each seasonal and season x day-type CSV into a 288-row mean-day profile under data/processed/average/.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC_DIRS = [
    ROOT / "data" / "processed" / "season",
    ROOT / "data" / "processed" / "season_daytype",
]
OUT_DIR = ROOT / "data" / "processed" / "average"

ANCHOR_DATE = pd.Timestamp("2025-01-01")


def average_daily_profile(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["SETTLEMENTDATE"] = pd.to_datetime(df["SETTLEMENTDATE"])

    tod = df["SETTLEMENTDATE"].dt.strftime("%H:%M:%S")
    grouped = (
        df.groupby(tod)
          .agg(TOTALDEMAND=("TOTALDEMAND", "mean"),
               RRP=("RRP", "mean"))
          .reset_index()
          .rename(columns={"SETTLEMENTDATE": "TIMEOFDAY"})
    )
    grouped.columns = ["TIMEOFDAY", "TOTALDEMAND", "RRP"]

    grouped["SETTLEMENTDATE"] = pd.to_datetime(
        ANCHOR_DATE.strftime("%Y-%m-%d") + " " + grouped["TIMEOFDAY"]
    )
    grouped = grouped.sort_values("SETTLEMENTDATE").reset_index(drop=True)

    region = df["REGION"].iloc[0] if "REGION" in df.columns else "VIC1"
    grouped.insert(0, "REGION", region)
    grouped["PERIODTYPE"] = "AVERAGE"
    return grouped[["REGION", "SETTLEMENTDATE", "TOTALDEMAND", "RRP", "PERIODTYPE"]]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for src in SRC_DIRS:
        for f in sorted(src.glob("*.csv")):
            df = pd.read_csv(f)
            avg = average_daily_profile(df)
            out = OUT_DIR / f.name
            avg.to_csv(out, index=False)
            written.append((out, len(avg)))
            print(f"{f.name:40s} -> {out.relative_to(ROOT)}  ({len(avg)} rows)")
    print(f"\nWrote {len(written)} files to {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
