"""
indicators_card.py
──────────────────
Key indicators section.  Every st.markdown call contains COMPLETE, self-closing
HTML — no open <div> left to be closed in a later call (Streamlit renders each
markdown block independently, so dangling tags appear as raw text).

Sparklines use st.plotly_chart with staticPlot=True and a fixed height of 44 px.
They are NOT wrapped in markdown divs to avoid the same issue.
"""
import math
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from utils.indicators import (
    fetch_financials,
    get_current_price_data,
    get_pe_pb,
    slice_sparkline,
)

# ─── COLORS ───────────────────────────────────────────────────────────────────
TICKER_COLORS = [
    "#4f8ef7", "#f75f4f", "#4fc98e", "#f7c74f",
    "#c44fff", "#ff914f", "#4ff7f0", "#f74fa0",
]

# ─── ONE-TIME CSS ─────────────────────────────────────────────────────────────
_CSS_DONE = False

def _inject_css() -> None:
    global _CSS_DONE
    if _CSS_DONE:
        return
    st.markdown(
        """
        <style>
        /* Prevent plotly sparklines from overflowing their column */
        [data-testid="stPlotlyChart"] > div { overflow: hidden !important; }
        /* Tighten vertical gap inside indicator columns */
        [data-testid="stVerticalBlock"] { gap: 2px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _CSS_DONE = True


# ─── FORMATTERS ───────────────────────────────────────────────────────────────
def _fmt_currency(val) -> str:
    if val is None:
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    if math.isnan(v):
        return "--"
    if abs(v) >= 1e9:
        return f"${v/1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.2f}"


def _fmt_ratio(val) -> str:
    if val is None:
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    return "--" if math.isnan(v) else f"{v:.2f}x"


def _fmt_pct(val) -> str:
    if val is None:
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    return "--" if math.isnan(v) else f"{v:.1f}%"


# ─── SPARKLINE ────────────────────────────────────────────────────────────────
def _sparkline(series: pd.Series, color: str, key: str) -> None:
    """Tiny line chart, 44 px tall, no axes, no toolbar."""
    fig = go.Figure(go.Scatter(
        x=list(range(len(series))),
        y=series.values,
        mode="lines",
        line=dict(color=color, width=1.5),
        hoverinfo="skip",
    ))
    fig.update_layout(
        height=44,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
        showlegend=False,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "staticPlot": True},
        key=key,
    )


def _spark_or_dash(series: pd.Series, period: str, quarterly: bool,
                   color: str, key: str) -> None:
    spark = slice_sparkline(series, period, quarterly) if not series.empty else pd.Series(dtype=float)
    if len(spark) >= 2:
        _sparkline(spark, color, key)
    else:
        st.caption("--")


# ─── MINI-CARD HEADER (self-contained HTML) ───────────────────────────────────
def _mini_card(label: str, value: str) -> None:
    """
    Renders a dark pill with LABEL on top and VALUE below.
    The HTML block is 100 % complete — no open tags.
    """
    st.markdown(
        f"""<div style="background:#1b2030;border:1px solid #2c3550;
                        border-radius:6px;padding:8px 10px 6px;margin-bottom:0;">
              <div style="font-size:9px;color:#5a6a90;text-transform:uppercase;
                          letter-spacing:1px;margin-bottom:2px;">{label}</div>
              <div style="font-size:13px;font-weight:700;color:#dce6f5;
                          font-family:monospace;">{value}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def _price_card(label: str, value: str, pct_str: str, chg_color: str) -> None:
    """Price card with percentage badge in the top-right corner."""
    st.markdown(
        f"""<div style="background:#1b2030;border:1px solid #2c3550;
                        border-radius:6px;padding:8px 10px 6px;margin-bottom:0;">
              <div style="display:flex;justify-content:space-between;
                          align-items:center;margin-bottom:2px;">
                <span style="font-size:9px;color:#5a6a90;text-transform:uppercase;
                             letter-spacing:1px;">{label}</span>
                <span style="font-size:9px;font-weight:600;
                             color:{chg_color};">{pct_str}</span>
              </div>
              <div style="font-size:13px;font-weight:700;color:#dce6f5;
                          font-family:monospace;">{value}</div>
            </div>""",
        unsafe_allow_html=True,
    )


# ─── TICKER CARD ──────────────────────────────────────────────────────────────
def _ticker_card(ticker: str, color: str, period: str, quarterly: bool) -> None:
    financials = fetch_financials(ticker, quarterly=quarterly)
    price_data = get_current_price_data(ticker)
    pe_val, pb_val = get_pe_pb(ticker)

    roe_val = financials["roe"].iloc[-1]             if not financials["roe"].empty             else None
    rev_val = financials["revenue"].iloc[-1]          if not financials["revenue"].empty          else None
    nd_val  = financials["net_debt_ebitda"].iloc[-1]  if not financials["net_debt_ebitda"].empty  else None

    price_series = financials.get("price", pd.Series(dtype=float))
    pl_series    = financials.get("pl",    pd.Series(dtype=float))
    pvp_series   = financials.get("pvp",   pd.Series(dtype=float))
    nd_series    = financials.get("net_debt_ebitda", pd.Series(dtype=float))
    roe_series   = financials.get("roe",   pd.Series(dtype=float))
    rev_series   = financials.get("revenue", pd.Series(dtype=float))

    up        = price_data["up"]
    pct       = price_data["pct"]
    chg_color = "#4fc98e" if up else "#f05a3d"
    spark_color = chg_color
    arrow     = "▲" if up else "▼"
    price_val = price_data["price"]
    price_str = f"${price_val:.2f}" if price_val else "--"
    pct_str   = f"{arrow} {abs(pct):.2f}%" if price_val else ""

    # ── Ticker header ─────────────────────────────────────────────────────────
    st.markdown(
        f"""<div style="font-family:monospace;font-size:14px;font-weight:700;
                        color:{color};padding:4px 0 8px;
                        border-bottom:1px solid #2c3550;margin-bottom:8px;">
              {ticker}
            </div>""",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        # Price
        _price_card("Price", price_str, pct_str, chg_color)
        _spark_or_dash(price_series, period, quarterly, spark_color,
                       f"sp_price_{ticker}_{period}")
        # P/L
        _mini_card("P/L", _fmt_ratio(pe_val))
        _spark_or_dash(pl_series, period, quarterly, color,
                       f"sp_pl_{ticker}_{period}")
        # Net Debt/EBITDA
        _mini_card("Net Debt/EBITDA", _fmt_ratio(nd_val))
        _spark_or_dash(nd_series, period, quarterly, color,
                       f"sp_nd_{ticker}_{period}")

    with col2:
        # ROE
        _mini_card("ROE", _fmt_pct(roe_val))
        _spark_or_dash(roe_series, period, quarterly, color,
                       f"sp_roe_{ticker}_{period}")
        # Revenue
        _mini_card("Revenue", _fmt_currency(rev_val))
        _spark_or_dash(rev_series, period, quarterly, color,
                       f"sp_rev_{ticker}_{period}")
        # P/VP
        _mini_card("P/VP", _fmt_ratio(pb_val))
        _spark_or_dash(pvp_series, period, quarterly, color,
                       f"sp_pvp_{ticker}_{period}")


# ─── MAIN RENDER ──────────────────────────────────────────────────────────────
def render_indicators(tickers: list[str], period: str, quarterly: bool = False) -> None:
    _inject_css()

    col_title, col_toggle = st.columns([5, 2])
    with col_title:
        st.markdown("### Key Indicators")
    with col_toggle:
        freq = st.radio(
            "freq", options=["Annual", "Quarterly"],
            horizontal=True, label_visibility="collapsed",
        )
        quarterly = (freq == "Quarterly")

    if not tickers:
        st.info("Select tickers in the sidebar to see indicators.")
        return

    n_cols = min(len(tickers), 4)
    cols   = st.columns(n_cols)

    for i, ticker in enumerate(tickers):
        color = TICKER_COLORS[i % len(TICKER_COLORS)]
        with cols[i % n_cols]:
            with st.container(border=True):
                _ticker_card(ticker=ticker, color=color, period=period, quarterly=quarterly)