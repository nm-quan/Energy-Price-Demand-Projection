"""
summary: plot price and demand for the six season x day-type CSVs as a 3x2 grid saved to figures/season_daytype_grid.png.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "data" / "processed" / "season_daytype"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

PRICE_COLOR = "#1f77b4"   # steel blue
DEMAND_COLOR = "#ff7f0e"  # orange
GRID_COLOR = "#d9d9d9"
TEXT = "#2b2b2b"

SEASONS = ("summer", "winter", "shoulder")
DAYTYPES = ("weekday", "weekend")


def month_ticks(df: pd.DataFrame) -> tuple[list[int], list[str]]:
    months = df["SETTLEMENTDATE"].dt.month
    change = months != months.shift()
    positions = df.index[change].tolist()
    labels = [df.loc[i, "SETTLEMENTDATE"].strftime("%b") for i in positions]
    return positions, labels


def plot_panel(ax_price, df: pd.DataFrame, title: str) -> None:
    df = df.sort_values("SETTLEMENTDATE").reset_index(drop=True)
    x = df.index.to_numpy()
    ax_demand = ax_price.twinx()

    ax_demand.plot(x, df["TOTALDEMAND"], color=DEMAND_COLOR,
                   linewidth=0.9, alpha=0.85)
    ax_price.plot(x, df["RRP"], color=PRICE_COLOR,
                  linewidth=0.7, alpha=0.9)

    positions, labels = month_ticks(df)
    for p in positions[1:]:  # skip the leftmost (axis edge)
        ax_price.axvline(p, color=GRID_COLOR, linewidth=0.8, alpha=0.7)
    ax_price.set_xticks(positions)
    ax_price.set_xticklabels(labels, fontsize=8)
    ax_price.set_xlim(x[0], x[-1])

    ax_price.set_title(title, color=TEXT, fontsize=10, fontweight="bold",
                       loc="left", pad=6)
    ax_price.tick_params(axis="y", colors=PRICE_COLOR, labelsize=7)
    ax_demand.tick_params(axis="y", colors=DEMAND_COLOR, labelsize=7)
    ax_price.tick_params(axis="x", colors=TEXT)
    ax_price.grid(True, axis="y", color=GRID_COLOR, alpha=0.6, linewidth=0.5)
    for spine in ("top",):
        ax_price.spines[spine].set_visible(False)
        ax_demand.spines[spine].set_visible(False)
    for spine in ("left", "right", "bottom"):
        ax_price.spines[spine].set_color(GRID_COLOR)
        ax_demand.spines[spine].set_color(GRID_COLOR)

    corr = df["TOTALDEMAND"].corr(df["RRP"])
    ax_price.text(0.99, 0.96, f"r = {corr:.3f}",
                  transform=ax_price.transAxes,
                  color=TEXT, fontsize=8, va="top", ha="right",
                  bbox=dict(facecolor="white", edgecolor=GRID_COLOR, pad=2))


def main() -> None:
    fig, axes = plt.subplots(3, 2, figsize=(15, 10), facecolor="white")
    fig.subplots_adjust(left=0.06, right=0.94, top=0.92, bottom=0.07,
                        hspace=0.45, wspace=0.22)

    for i, season in enumerate(SEASONS):
        for j, daytype in enumerate(DAYTYPES):
            path = IN_DIR / f"vic1_2025_{season}_{daytype}.csv"
            df = pd.read_csv(path, parse_dates=["SETTLEMENTDATE"])
            plot_panel(axes[i, j], df,
                       f"{season.title()} — {daytype.title()}")

    fig.suptitle("VIC1 · 2025 · Price vs Demand by Season & Day-type",
                 color=TEXT, fontsize=14, fontweight="bold", y=0.975)

    # shared legend / axis labels
    fig.text(0.5, 0.02, "Month", color=TEXT, ha="center", fontsize=10)
    fig.text(0.012, 0.5, "Price ($/MWh)", color=PRICE_COLOR, va="center",
             rotation="vertical", fontsize=10, fontweight="bold")
    fig.text(0.985, 0.5, "Demand (MW)", color=DEMAND_COLOR, va="center",
             rotation="vertical", fontsize=10, fontweight="bold")

    out_path = FIG_DIR / "season_daytype_grid.png"
    fig.savefig(out_path, dpi=150, facecolor="white", bbox_inches="tight")
    print(f"Saved figure: {out_path}")


if __name__ == "__main__":
    main()
