"""
summary: print VIC1 price and demand outliers (|z| > 3) for a given month from data/raw/.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw"


def load_month(month: int) -> pd.DataFrame:
    f = DATA_DIR / f"vic1_2025{month:02d}.csv"
    return pd.read_csv(f, parse_dates=["SETTLEMENTDATE"])


def outliers(df: pd.DataFrame, col: str, k: float = 3.0) -> pd.DataFrame:
    mean = df[col].mean()
    std = df[col].std()
    mask = (df[col] - mean).abs() > k * std
    out = df.loc[mask, ["SETTLEMENTDATE", "TOTALDEMAND", "RRP"]].copy()
    out["z"] = ((df.loc[mask, col] - mean) / std).round(2)
    return out.sort_values("z", key=lambda s: s.abs(), ascending=False)


for month in (6, 7):
    df = load_month(month)
    print(f"\n=== Month {month}/2025 — n={len(df)} ===")
    print(f"RRP: mean={df['RRP'].mean():.2f}  std={df['RRP'].std():.2f}  "
          f"min={df['RRP'].min():.2f}  max={df['RRP'].max():.2f}")
    print(f"DEM: mean={df['TOTALDEMAND'].mean():.0f}  std={df['TOTALDEMAND'].std():.0f}  "
          f"min={df['TOTALDEMAND'].min():.0f}  max={df['TOTALDEMAND'].max():.0f}")

    print("\nPRICE outliers (|z|>3):")
    print(outliers(df, "RRP").head(15).to_string(index=False))

    print("\nDEMAND outliers (|z|>3):")
    print(outliers(df, "TOTALDEMAND").head(15).to_string(index=False))
