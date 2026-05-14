"""
summary: interactive Streamlit UI for tuning the demand-response model against any of the 9 averaged daily profiles in data/processed/average/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from demand_model import model

ROOT = Path(__file__).resolve().parent.parent
AVERAGE_DIR = ROOT / "data" / "processed" / "average"

BG = "#0d1b2a"
PRICE_COLOR = "#d63384"
ORIG_COLOR = "#3ddbd9"
MOD_COLOR = "#ffb703"
RED_BAND = "#ff5d73"
FREE_BAND = "#06d6a0"
TEXT = "#e0e1dd"
MUTED = "#8d99ae"


def humanize(name: str) -> str:
    stem = Path(name).stem.replace("vic1_2025_", "")
    return stem.replace("_", " · ").title()


@st.cache_data(show_spinner=False)
def list_average_files() -> list[Path]:
    return sorted(AVERAGE_DIR.glob("vic1_2025_*.csv"))


@st.cache_data(show_spinner=False)
def load_profile(path_str: str) -> pd.DataFrame:
    df = pd.read_csv(path_str, parse_dates=["SETTLEMENTDATE"])
    return df.sort_values("SETTLEMENTDATE").reset_index(drop=True)


def style_axes(*axes):
    for a in axes:
        a.set_facecolor(BG)
        a.tick_params(colors=TEXT, labelsize=9)
        for s in a.spines.values():
            s.set_color(MUTED)


def _shade(ax, interval, color, label):
    if interval is None:
        return
    a, b = interval
    base = pd.Timestamp("2025-01-01")
    if a < b:
        ax.axvspan(base + pd.Timedelta(hours=a),
                   base + pd.Timedelta(hours=b),
                   color=color, alpha=0.12, label=label)
    else:
        ax.axvspan(base + pd.Timedelta(hours=a),
                   base + pd.Timedelta(hours=24),
                   color=color, alpha=0.12, label=label)
        ax.axvspan(base, base + pd.Timedelta(hours=b),
                   color=color, alpha=0.12)


def make_chart(df: pd.DataFrame, modelled: pd.DataFrame,
               red_iv, free_iv, show_price: bool) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(13, 5.5), facecolor=BG)

    _shade(ax, red_iv, RED_BAND, "Reduction window")
    _shade(ax, free_iv, FREE_BAND, "Free window")

    ax.plot(df["SETTLEMENTDATE"], df["TOTALDEMAND"],
            color=ORIG_COLOR, linewidth=2.0, alpha=0.95, label="Original Demand")
    ax.plot(modelled["SETTLEMENTDATE"], modelled["MODELLED_DEMAND"],
            color=MOD_COLOR, linewidth=2.0, alpha=0.95,
            linestyle="--", label="Modelled Demand")
    ax.fill_between(df["SETTLEMENTDATE"], df["TOTALDEMAND"],
                    color=ORIG_COLOR, alpha=0.08)

    ax.set_ylabel("Demand (MW)", color=TEXT, fontsize=11, fontweight="bold")
    ax.set_xlabel("Hour of day", color=TEXT, fontsize=10)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    style_axes(ax)
    ax.grid(True, color=MUTED, alpha=0.15, linewidth=0.5)

    if show_price:
        ax_p = ax.twinx()
        ax_p.plot(df["SETTLEMENTDATE"], df["RRP"],
                  color=PRICE_COLOR, linewidth=1.4, alpha=0.7,
                  label="RRP ($/MWh)")
        ax_p.set_ylabel("RRP ($/MWh)", color=PRICE_COLOR,
                        fontsize=11, fontweight="bold")
        ax_p.tick_params(axis="y", colors=PRICE_COLOR, labelsize=9)
        for s in ax_p.spines.values():
            s.set_color(MUTED)
        lines_a, labels_a = ax.get_legend_handles_labels()
        lines_b, labels_b = ax_p.get_legend_handles_labels()
        leg = ax.legend(lines_a + lines_b, labels_a + labels_b,
                        loc="upper left", framealpha=0.4, fontsize=9)
    else:
        leg = ax.legend(loc="upper left", framealpha=0.4, fontsize=9)

    for t in leg.get_texts():
        t.set_color(TEXT)

    fig.tight_layout()
    return fig


def parse_interval(values: tuple[int, int]):
    a, b = values
    if a == b:
        return None
    return (a, b)


st.set_page_config(page_title="Demand Tuner", layout="wide")

st.markdown(
    f"""
    <style>
      .stApp {{ background-color: {BG}; color: {TEXT}; }}
      section[data-testid="stSidebar"] {{ background-color: #0a1320; }}
      h1, h2, h3, h4, label, p, span {{ color: {TEXT} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Demand Model Tuner — VIC1 2025 Daily Profiles")

files = list_average_files()
if not files:
    st.error(f"No averaged CSVs found under {AVERAGE_DIR}. "
             f"Run `python demand/build_average.py` first.")
    st.stop()

with st.sidebar:
    st.header("Profile")
    profile_path = st.selectbox(
        "Average profile",
        options=files,
        format_func=lambda p: humanize(p.name),
        index=next((i for i, p in enumerate(files) if "summer_weekday" in p.name), 0),
    )

    st.header("Reduction interval (exclude free interval automatic)")
    red_range = st.slider(
        "Hours of day — reduction",
        min_value=0, max_value=24, value=(17, 21), step=1,
        help="Set start == end to disable.",
    )
    peak_reduction = st.slider(
        "Peak reduction (%)", min_value=0.0, max_value=50.0, value=15.0, step=0.5,
    )

    st.header("Free interval (rebound / pre-load)")
    free_range = st.slider(
        "Hours of day — free",
        min_value=0, max_value=24, value=(11, 15), step=1,
        help="Set start == end to disable.",
    )
    rebound = st.slider(
        "Rebound (%)", min_value=0.0, max_value=50.0, value=8.0, step=0.5,
    )

    st.header("Display")
    show_price = st.checkbox("Overlay RRP price", value=False)

red_iv = parse_interval(red_range)
free_iv = parse_interval(free_range)

df = load_profile(str(profile_path))

modelled_df, _ = model(
    init_data=df,
    reduction_interval=red_iv,
    free_interval=free_iv,
    peak_reduction=peak_reduction,
    rebound_percentage=rebound,
    save=False,
)

orig_energy = df["TOTALDEMAND"].sum() / 12     # 5-min intervals -> MWh
mod_energy = modelled_df["MODELLED_DEMAND"].sum() / 12
delta_pct = (mod_energy - orig_energy) / orig_energy * 100 if orig_energy else 0.0

orig_peak = df["TOTALDEMAND"].max()
mod_peak = modelled_df["MODELLED_DEMAND"].max()
peak_delta_pct = (mod_peak - orig_peak) / orig_peak * 100 if orig_peak else 0.0

c1, c2, c3 = st.columns(3)
c1.metric("Daily energy — original (MWh)", f"{orig_energy:,.0f}")
c2.metric("Daily energy — modelled (MWh)", f"{mod_energy:,.0f}", f"{delta_pct:+.2f}%")
c3.metric("Peak demand (MW)", f"{mod_peak:,.0f}", f"{peak_delta_pct:+.2f}%")

st.pyplot(make_chart(df, modelled_df, red_iv, free_iv, show_price), clear_figure=True)

dl_orig = df[["REGION", "SETTLEMENTDATE", "TOTALDEMAND", "RRP"]].to_csv(index=False)
dl_mod = modelled_df[
    ["REGION", "SETTLEMENTDATE", "ORIGINAL_DEMAND", "MODELLED_DEMAND", "RRP"]
].to_csv(index=False)

d1, d2 = st.columns(2)
d1.download_button(
    label="Download original CSV",
    data=dl_orig,
    file_name=f"original_{profile_path.stem}.csv",
    mime="text/csv",
    width="stretch",
)
d2.download_button(
    label="Download modelled CSV",
    data=dl_mod,
    file_name=f"modelled_{profile_path.stem}.csv",
    mime="text/csv",
    width="stretch",
)

with st.expander("Sample of modelled data"):
    st.dataframe(
        modelled_df[["SETTLEMENTDATE", "ORIGINAL_DEMAND", "MODELLED_DEMAND", "RRP"]],
        width="stretch",
        height=260,
    )
