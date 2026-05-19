"""
summary: Streamlit UI for tuning the demand-response model and projecting
dispatch cost impact against VIC1 2025 averaged daily profiles.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from demand_model import model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "energy"))
from energy_model import run_dispatch 
ROOT = Path(__file__).resolve().parent.parent
AVERAGE_DIR = ROOT / "data" / "processed" / "average"


INK = "#0f172a"          # primary text
INK_SOFT = "#334155"     # secondary text
INK_MUTE = "#64748b"     # tertiary / captions
LINE = "#e2e8f0"         # borders, gridlines
CANVAS = "#ffffff"       # cards
SURFACE = "#f8fafc"      # page background
ACCENT = "#1e40af"       # single accent — deep indigo


C_ORIG = "#1e40af"       # original demand
C_MOD = "#ea580c"        # modelled demand
C_PRICE = "#7c3aed"      # RRP line
BAND_RED = "#fecaca"     # reduction window shade
BAND_GREEN = "#bbf7d0"   # free window shade


GEN_COLORS = {
    "Coal":        "#475569",
    "Gas Steam":   "#3b82f6",
    "Gas Peaker":  "#f59e0b",
    "Hydro Gen":   "#10b981",
    "Battery Dis": "#8b5cf6",
    "Hydro Pump":  "#a8a29e",
    "Battery Chg": "#c7d2fe",
}


# ---------- Helpers ----------
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


def _apply_axis_style(ax: plt.Axes) -> None:
    ax.set_facecolor(CANVAS)
    ax.tick_params(colors=INK_SOFT, labelsize=9, length=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
        ax.spines[side].set_linewidth(0.8)
    ax.grid(True, color=LINE, alpha=1.0, linewidth=0.5, axis="y")
    ax.set_axisbelow(True)


def _shade(ax, interval, color, label):
    if interval is None:
        return
    a, b = interval
    base = pd.Timestamp("2025-01-01")
    if a < b:
        ax.axvspan(base + pd.Timedelta(hours=a),
                   base + pd.Timedelta(hours=b),
                   color=color, alpha=0.35, label=label,
                   linewidth=0)
    else:
        ax.axvspan(base + pd.Timedelta(hours=a),
                   base + pd.Timedelta(hours=24),
                   color=color, alpha=0.35, label=label, linewidth=0)
        ax.axvspan(base, base + pd.Timedelta(hours=b),
                   color=color, alpha=0.35, linewidth=0)


def make_demand_chart(df: pd.DataFrame, modelled: pd.DataFrame,
                      red_iv, free_iv, show_price: bool) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(14, 5.2), facecolor=CANVAS)
    fig.subplots_adjust(right=0.83, top=0.93, bottom=0.14, left=0.07)

    _shade(ax, red_iv, BAND_RED, "Reduction window")
    _shade(ax, free_iv, BAND_GREEN, "Free window")

    ax.plot(df["SETTLEMENTDATE"], df["TOTALDEMAND"],
            color=C_ORIG, linewidth=2.0, label="Original")
    ax.plot(modelled["SETTLEMENTDATE"], modelled["MODELLED_DEMAND"],
            color=C_MOD, linewidth=2.0, linestyle="--", label="Modelled")

    ax.set_ylabel("Demand (MW)", color=INK_SOFT, fontsize=10)
    ax.set_xlabel("")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    _apply_axis_style(ax)

    if show_price:
        ax_p = ax.twinx()
        ax_p.plot(df["SETTLEMENTDATE"], df["RRP"],
                  color=C_PRICE, linewidth=1.3, alpha=0.85, label="RRP")
        ax_p.set_ylabel("RRP ($/MWh)", color=INK_SOFT, fontsize=10)
        ax_p.tick_params(axis="y", colors=INK_SOFT, labelsize=9, length=0)
        for side in ("top", "right", "left", "bottom"):
            ax_p.spines[side].set_visible(False)
        ax_p.spines["right"].set_visible(True)
        ax_p.spines["right"].set_color(LINE)
        lines_a, labels_a = ax.get_legend_handles_labels()
        lines_b, labels_b = ax_p.get_legend_handles_labels()
        leg = ax.legend(lines_a + lines_b, labels_a + labels_b,
                        loc="center left", bbox_to_anchor=(1.06, 0.5),
                        frameon=False, fontsize=9)
    else:
        leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                        frameon=False, fontsize=9)

    for t in leg.get_texts():
        t.set_color(INK_SOFT)
    return fig


def dispatch_stack_fig(dispatch_df: pd.DataFrame, title: str,
                       y_lim: tuple[float, float] | None = None) -> plt.Figure:
    hours = dispatch_df.index
    pos_keys = ["Coal", "Gas Steam", "Gas Peaker", "Hydro Gen", "Battery Dis"]
    pos_vals = [
        dispatch_df["Coal_MW"],
        dispatch_df["Gas_Steam_MW"],
        dispatch_df["Gas_Peaker_MW"],
        dispatch_df["Hydro_Gen_MW"],
        dispatch_df["Batt_Discharge_MW"],
    ]
    neg_keys = ["Hydro Pump", "Battery Chg"]
    neg_vals = [-dispatch_df["Hydro_Pump_MW"], -dispatch_df["Batt_Charge_MW"]]

    fig, ax = plt.subplots(figsize=(14, 5.4), facecolor=CANVAS)
    fig.subplots_adjust(right=0.83, top=0.90, bottom=0.13, left=0.07)

    ax.stackplot(hours, pos_vals, labels=pos_keys,
                 colors=[GEN_COLORS[k] for k in pos_keys], alpha=0.92,
                 edgecolor=CANVAS, linewidth=0.5)
    ax.stackplot(hours, [-v for v in neg_vals], labels=neg_keys,
                 colors=[GEN_COLORS[k] for k in neg_keys], alpha=0.75,
                 edgecolor=CANVAS, linewidth=0.5)
    ax.plot(hours, dispatch_df["Demand_MW"], color=INK,
            linewidth=2.2, marker="o", markersize=4,
            markerfacecolor=CANVAS, markeredgewidth=1.4,
            label="Demand", zorder=10)

    ax.axhline(0, color=LINE, linewidth=0.8)
    ax.set_xlabel("Hour of day", color=INK_SOFT, fontsize=10)
    ax.set_ylabel("Power (MW)", color=INK_SOFT, fontsize=10)
    ax.set_title(title, color=INK, fontsize=12, fontweight="600",
                 loc="left", pad=10)
    ax.set_xticks(hours[::2])
    ax.set_xlim(hours.min(), hours.max())
    if y_lim is not None:
        ax.set_ylim(*y_lim)
    _apply_axis_style(ax)

    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                    frameon=False, fontsize=9,
                    handlelength=1.6, handleheight=1.0,
                    labelspacing=0.8, borderaxespad=0)
    for t in leg.get_texts():
        t.set_color(INK_SOFT)
    return fig


def parse_interval(values: tuple[int, int]):
    a, b = values
    return None if a == b else (a, b)


def to_hourly(series: pd.Series, timestamps: pd.Series) -> dict[int, float]:
    s = pd.Series(series.values, index=pd.to_datetime(timestamps.values))
    hourly = s.resample("1h").mean()
    return {i: float(v) for i, v in enumerate(hourly.values[:24])}


# ---------- Page ----------
st.set_page_config(page_title="VIC1 Demand & Dispatch",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown(
    f"""
    <style>
      /* ---------- Base ---------- */
      html, body, .stApp, [data-testid="stAppViewContainer"] {{
        background-color: {SURFACE} !important;
        color: {INK} !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                     "Helvetica Neue", Arial, sans-serif !important;
      }}
      .stApp *, [data-testid="stAppViewContainer"] * {{
        color: {INK};
      }}
      .block-container {{
        padding-top: 2.2rem; padding-bottom: 3rem;
        max-width: 1400px;
      }}

      /* ---------- Sidebar ---------- */
      section[data-testid="stSidebar"],
      section[data-testid="stSidebar"] > div {{
        background-color: {CANVAS} !important;
        border-right: 1px solid {LINE};
      }}
      section[data-testid="stSidebar"] * {{ color: {INK} !important; }}
      section[data-testid="stSidebar"] h2,
      section[data-testid="stSidebar"] h3 {{
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        margin-top: 1.4rem !important;
        margin-bottom: 0.4rem !important;
      }}
      section[data-testid="stSidebar"] label,
      section[data-testid="stSidebar"] label p {{
        color: {INK_SOFT} !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
      }}

      /* ---------- Headings ---------- */
      h1, h1 span {{
        color: {INK} !important;
        font-weight: 600 !important;
        font-size: 1.7rem !important;
        letter-spacing: -0.02em;
        margin-bottom: 0.15rem;
      }}
      h2, h2 span {{
        color: {INK} !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        letter-spacing: -0.005em;
        margin-top: 2.2rem !important;
        padding-top: 1.4rem;
        border-top: 1px solid {LINE};
      }}
      h3, h4, h3 span, h4 span {{
        color: {INK} !important;
        font-weight: 600 !important;
      }}
      p, label, span, div, li {{ color: {INK} !important; }}
      .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li {{
        color: {INK} !important;
      }}

      /* ---------- Inputs (selectbox, slider, checkbox) ---------- */
      [data-baseweb="select"] > div,
      [data-baseweb="select"] input {{
        background-color: {CANVAS} !important;
        color: {INK} !important;
        border-color: {LINE} !important;
      }}
      [data-baseweb="select"] svg {{ color: {INK_SOFT} !important;
                                     fill: {INK_SOFT} !important; }}
      [role="listbox"], [role="listbox"] * {{
        background-color: {CANVAS} !important;
        color: {INK} !important;
      }}
      [data-baseweb="slider"] [role="slider"] {{
        background-color: {ACCENT} !important;
        box-shadow: none !important;
      }}
      [data-baseweb="slider"] div[style*="background"] {{
        color: {INK_SOFT} !important;
      }}
      [data-testid="stCheckbox"] label,
      [data-testid="stCheckbox"] label p {{ color: {INK} !important; }}

      /* ---------- Metric cards ---------- */
      [data-testid="stMetric"] {{
        background-color: {CANVAS} !important;
        border: 1px solid {LINE};
        border-radius: 10px;
        padding: 1rem 1.2rem;
      }}
      [data-testid="stMetric"] * {{ color: {INK} !important; }}
      [data-testid="stMetricLabel"],
      [data-testid="stMetricLabel"] p,
      [data-testid="stMetricLabel"] div {{
        color: {INK_MUTE} !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
      }}
      [data-testid="stMetricValue"],
      [data-testid="stMetricValue"] div {{
        color: {INK} !important;
        font-weight: 600 !important;
        font-size: 1.5rem !important;
      }}
      [data-testid="stMetricDelta"] {{
        font-size: 0.82rem !important;
        font-weight: 500 !important;
      }}
      [data-testid="stMetricDelta"] svg {{ display: inline-block; }}

      /* ---------- Buttons ---------- */
      .stButton > button {{
        background-color: {ACCENT} !important;
        color: #ffffff !important;
        border: 1px solid {ACCENT} !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 0.5rem 1.25rem !important;
        font-size: 0.9rem !important;
        transition: background-color 120ms ease;
      }}
      .stButton > button * {{ color: #ffffff !important; }}
      .stButton > button:hover {{
        background-color: #1e3a8a !important;
        border-color: #1e3a8a !important;
      }}
      .stDownloadButton > button {{
        background-color: {CANVAS} !important;
        color: {INK} !important;
        border: 1px solid {LINE} !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
      }}
      .stDownloadButton > button * {{ color: {INK} !important; }}
      .stDownloadButton > button:hover {{
        border-color: {INK_MUTE} !important;
        background-color: {CANVAS} !important;
      }}

      /* ---------- Expanders & dataframes ---------- */
      [data-testid="stExpander"] {{
        border: 1px solid {LINE};
        border-radius: 8px;
        background-color: {CANVAS} !important;
      }}
      [data-testid="stExpander"] summary,
      [data-testid="stExpander"] summary * {{ color: {INK} !important; }}
      [data-testid="stExpander"] svg {{ color: {INK_SOFT} !important;
                                        fill: {INK_SOFT} !important; }}
      [data-testid="stDataFrame"] * {{ color: {INK} !important; }}

      /* ---------- Misc ---------- */
      .stCaption, [data-testid="stCaptionContainer"],
      [data-testid="stCaptionContainer"] * {{ color: {INK_MUTE} !important; }}
      hr {{ border-color: {LINE} !important; margin: 1.5rem 0; }}
      [data-testid="stAlert"] {{
        background-color: #fef2f2 !important;
        border: 1px solid #fecaca !important;
        color: #991b1b !important;
      }}
      [data-testid="stAlert"] * {{ color: #991b1b !important; }}
      .stSpinner > div {{ color: {INK_SOFT} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


files = list_average_files()
if not files:
    st.error(f"No averaged CSVs found under {AVERAGE_DIR}. "
             f"Run `python demand/build_average.py` first.")
    st.stop()

with st.sidebar:
    st.markdown("### Profile")
    profile_path = st.selectbox(
        "Average profile",
        options=files,
        format_func=lambda p: humanize(p.name),
        index=next((i for i, p in enumerate(files) if "summer_weekday" in p.name), 0),
        label_visibility="collapsed",
    )

    st.markdown("### Reduction Window")
    red_range = st.slider(
        "Hours", min_value=0, max_value=24, value=(17, 21), step=1,
        help="Set start == end to disable.",
    )
    peak_reduction = st.slider(
        "Peak reduction (%)", min_value=0.0, max_value=50.0, value=15.0, step=0.5,
    )

    st.markdown("### Free Window")
    free_range = st.slider(
        "Hours ", min_value=0, max_value=24, value=(11, 15), step=1,
        help="Set start == end to disable.",
    )
    rebound = st.slider(
        "Rebound (%)", min_value=0.0, max_value=50.0, value=8.0, step=0.5,
    )

    st.markdown("### Display")
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

orig_energy = df["TOTALDEMAND"].sum() / 12
mod_energy = modelled_df["MODELLED_DEMAND"].sum() / 12
delta_pct = (mod_energy - orig_energy) / orig_energy * 100 if orig_energy else 0.0

orig_peak = df["TOTALDEMAND"].max()
mod_peak = modelled_df["MODELLED_DEMAND"].max()
peak_delta_pct = (mod_peak - orig_peak) / orig_peak * 100 if orig_peak else 0.0

# ---------- Demand section ----------
st.markdown("## Demand response")

c1, c2, c3 = st.columns(3)
c1.metric("Original energy", f"{orig_energy:,.0f} MWh")
c2.metric("Modelled energy", f"{mod_energy:,.0f} MWh", f"{delta_pct:+.2f}%")
c3.metric("Peak demand", f"{mod_peak:,.0f} MW", f"{peak_delta_pct:+.2f}%")

st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
st.pyplot(make_demand_chart(df, modelled_df, red_iv, free_iv, show_price),
          clear_figure=True)

# ---------- Downloads ----------
dl_orig = df[["REGION", "SETTLEMENTDATE", "TOTALDEMAND", "RRP"]].to_csv(index=False)
dl_mod = modelled_df[
    ["REGION", "SETTLEMENTDATE", "ORIGINAL_DEMAND", "MODELLED_DEMAND", "RRP"]
].to_csv(index=False)

d1, d2, _ = st.columns([1, 1, 2])
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

with st.expander("Modelled data — preview"):
    st.dataframe(
        modelled_df[["SETTLEMENTDATE", "ORIGINAL_DEMAND", "MODELLED_DEMAND", "RRP"]],
        width="stretch",
        height=260,
    )

# ---------- Dispatch section ----------
st.markdown("## Price projection")
st.markdown(
    f"<p style='color:{INK_MUTE} !important; margin-top:-0.5rem; "
    f"font-size:0.95rem;'>"
    f"Runs an economic dispatch LP (coal, gas, battery, pumped hydro) on both "
    f"the original and modelled profiles and compares optimal cost.</p>",
    unsafe_allow_html=True,
)

run = st.button("Run price projection", type="primary")

if run:
    with st.spinner("Solving LP for both demand profiles..."):
        orig_hourly = to_hourly(df["TOTALDEMAND"], df["SETTLEMENTDATE"])
        mod_hourly = to_hourly(modelled_df["MODELLED_DEMAND"],
                               modelled_df["SETTLEMENTDATE"])
        orig_dispatch, orig_cost, orig_status = run_dispatch(orig_hourly)
        mod_dispatch, mod_cost, mod_status = run_dispatch(mod_hourly)

    if orig_status != "Optimal" or mod_status != "Optimal":
        st.error(
            f"LP did not solve to optimality. "
            f"Original: {orig_status} · Modelled: {mod_status}."
        )
    else:
        savings = orig_cost - mod_cost
        savings_pct = (savings / orig_cost * 100) if orig_cost else 0.0

        m1, m2, m3 = st.columns(3)
        m1.metric("Original cost", f"${orig_cost:,.0f}")
        m2.metric("Modelled cost", f"${mod_cost:,.0f}", f"{-savings_pct:+.2f}%")
        m3.metric("Savings", f"${savings:,.0f}", f"{savings_pct:+.2f}%")

        def _gross(d):
            return (d["Coal_MW"] + d["Gas_Steam_MW"] + d["Gas_Peaker_MW"]
                    + d["Hydro_Gen_MW"] + d["Batt_Discharge_MW"]).max()

        def _absorb(d):
            return (-d["Hydro_Pump_MW"] - d["Batt_Charge_MW"]).max()

        y_top = max(_gross(orig_dispatch), _gross(mod_dispatch)) * 1.05
        y_bot = -max(_absorb(orig_dispatch), _absorb(mod_dispatch), 1) * 1.15
        y_lim = (y_bot, y_top)

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
        st.pyplot(dispatch_stack_fig(orig_dispatch,
                                     "Original demand — dispatch",
                                     y_lim=y_lim), clear_figure=True)
        st.pyplot(dispatch_stack_fig(mod_dispatch,
                                     "Modelled demand — dispatch",
                                     y_lim=y_lim), clear_figure=True)

        e1, e2 = st.columns(2)
        with e1.expander("Hourly dispatch — original"):
            st.dataframe(orig_dispatch.round(1), width="stretch", height=320)
        with e2.expander("Hourly dispatch — modelled"):
            st.dataframe(mod_dispatch.round(1), width="stretch", height=320)
