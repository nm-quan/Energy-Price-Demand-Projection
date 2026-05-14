"""
summary: split the yearly merged CSV into three season files (summer/winter/shoulder) under data/processed/season/.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / "data" / "processed" / "merged" / "vic1_2025.csv"
OUT_DIR = ROOT / "data" / "processed" / "season"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEASON_MAP = {
    12: "summer", 1: "summer", 2: "summer",
    6: "winter", 7: "winter", 8: "winter",
    3: "shoulder", 4: "shoulder", 5: "shoulder",
    9: "shoulder", 10: "shoulder", 11: "shoulder",
}


def main() -> None:
    if not IN_FILE.exists():
        raise SystemExit(f"Merged file not found: {IN_FILE}. "
                         "Run merge.py first.")

    df = pd.read_csv(IN_FILE, parse_dates=["SETTLEMENTDATE"])
    df["season"] = df["SETTLEMENTDATE"].dt.month.map(SEASON_MAP)

    print(f"{'File':<30} {'Rows':>8}")
    print("-" * 40)
    for season in ("summer", "winter", "shoulder"):
        subset = df[df["season"] == season].drop(columns=["season"])
        name = f"vic1_2025_{season}.csv"
        out_path = OUT_DIR / name
        subset.to_csv(out_path, index=False)
        print(f"{name:<30} {len(subset):>8}")

    print(f"\nWritten to: {OUT_DIR}")


if __name__ == "__main__":
    main()
