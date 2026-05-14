"""
summary: concatenate the 12 cleaned monthly CSVs into one yearly file at data/processed/merged/vic1_2025.csv.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "data" / "processed" / "cleaned"
OUT_DIR = ROOT / "data" / "processed" / "merged"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "vic1_2025.csv"


def main() -> None:
    files = sorted(IN_DIR.glob("vic1_2025*.csv"))
    if not files:
        raise SystemExit(f"No cleaned files found in {IN_DIR}. "
                         "Run preprocess.py first.")

    frames = [pd.read_csv(f, parse_dates=["SETTLEMENTDATE"]) for f in files]
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values("SETTLEMENTDATE").reset_index(drop=True)
    merged = merged.drop_duplicates(subset=["SETTLEMENTDATE"])

    merged.to_csv(OUT_FILE, index=False)
    print(f"Merged {len(files)} files -> {OUT_FILE}")
    print(f"Rows: {len(merged):,}")
    print(f"Range: {merged['SETTLEMENTDATE'].min()} -> "
          f"{merged['SETTLEMENTDATE'].max()}")


if __name__ == "__main__":
    main()
