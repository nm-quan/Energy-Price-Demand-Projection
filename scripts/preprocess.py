"""
summary: forward-fill nulls in each raw monthly VIC1 CSV and write a cleaned copy to data/processed/cleaned/.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed" / "cleaned"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NUMERIC_COLS = ["TOTALDEMAND", "RRP"]


def preprocess_file(path: Path) -> dict:
    df = pd.read_csv(path, parse_dates=["SETTLEMENTDATE"])
    df = df.sort_values("SETTLEMENTDATE").reset_index(drop=True)

    null_counts = {col: int(df[col].isna().sum()) for col in NUMERIC_COLS}
    df[NUMERIC_COLS] = df[NUMERIC_COLS].ffill().bfill()

    skewness = {col: float(df[col].skew()) for col in NUMERIC_COLS}

    out_path = OUT_DIR / path.name
    df.to_csv(out_path, index=False)

    return {
        "file": path.name,
        "rows": len(df),
        "nulls": null_counts,
        "skewness": skewness,
        "output": out_path,
    }


def main() -> None:
    raw_files = sorted(RAW_DIR.glob("vic1_2025*.csv"))
    if not raw_files:
        raise SystemExit(f"No raw monthly files found in {RAW_DIR}")

    print(f"Found {len(raw_files)} files in {RAW_DIR}\n")
    print(f"{'File':<20} {'Rows':>6} {'NullDem':>8} {'NullRRP':>8} "
          f"{'SkewDem':>10} {'SkewRRP':>10}")
    print("-" * 66)

    for path in raw_files:
        r = preprocess_file(path)
        print(f"{r['file']:<20} {r['rows']:>6} "
              f"{r['nulls']['TOTALDEMAND']:>8} {r['nulls']['RRP']:>8} "
              f"{r['skewness']['TOTALDEMAND']:>10.4f} "
              f"{r['skewness']['RRP']:>10.4f}")

    print(f"\nCleaned files written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
