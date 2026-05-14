"""
summary: plot one month of VIC1 price + demand with a dual y-axis and save the figure to figures/price_demand_1month.png.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "raw" / "vic1_202501.csv"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

BG = "#0d1b2a"
PANEL = "#0d1b2a"
PRICE_COLOR = "#d63384"
DEMAND_COLOR = "#3ddbd9"
TEXT = "#e0e1dd"
MUTED = "#8d99ae"


def main() -> None:
    df = pd.read_csv(DATA_FILE, parse_dates=["SETTLEMENTDATE"])
    df = df.sort_values("SETTLEMENTDATE").reset_index(drop=True)

    corr = df["TOTALDEMAND"].corr(df["RRP"], method="pearson")
    print(f"Pearson correlation (demand vs price): {corr:.4f}")

    fig, ax_price = plt.subplots(figsize=(14, 7), facecolor=BG)
    fig.subplots_adjust(left=0.07, right=0.93, top=0.92, bottom=0.12)
    ax_price.set_facecolor(PANEL)
    ax_demand = ax_price.twinx()

    ax_demand.fill_between(df["SETTLEMENTDATE"], df["TOTALDEMAND"],
                           color=DEMAND_COLOR, alpha=0.15)
    ax_demand.plot(df["SETTLEMENTDATE"], df["TOTALDEMAND"],
                   color=DEMAND_COLOR, linewidth=1.2, label="Demand (MW)")
    ax_price.plot(df["SETTLEMENTDATE"], df["RRP"],
                  color=PRICE_COLOR, linewidth=1.0, label="Price ($/MWh)")

    ax_price.set_ylabel("PRICE ($/MWh)", color=TEXT, fontsize=9, fontweight="bold")
    ax_demand.set_ylabel("DEMAND (MW)", color=TEXT, fontsize=9, fontweight="bold")
    ax_price.tick_params(axis="y", colors=TEXT, labelsize=8)
    ax_demand.tick_params(axis="y", colors=TEXT, labelsize=8)
    ax_price.tick_params(axis="x", colors=TEXT, labelsize=8)

    for spine in ax_price.spines.values():
        spine.set_color(MUTED)
    for spine in ax_demand.spines.values():
        spine.set_color(MUTED)

    ax_price.grid(True, color=MUTED, alpha=0.15, linewidth=0.5)

    region = df["REGION"].iloc[0]
    month = df["SETTLEMENTDATE"].dt.strftime("%Y-%m").iloc[0]
    fig.suptitle(f"{region}  ·  {month}  ·  Pearson r = {corr:.4f}",
                 color=TEXT, fontsize=11, fontweight="bold", y=0.98)

    fig.autofmt_xdate()

    out_path = FIG_DIR / "price_demand_1month.png"
    fig.savefig(out_path, dpi=150, facecolor=BG)
    print(f"Saved figure: {out_path}")


if __name__ == "__main__":
    main()
