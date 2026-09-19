import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import pytz

from utils.data import fetch_intraday, fetch_prices, PERIOD_MAP

ET = pytz.timezone("America/New_York")

COLORS = [
    "#4f8ef7", "#f75f4f", "#4fc98e", "#f7c74f",
    "#c44fff", "#ff914f", "#4ff7f0", "#f74fa0",
]

# ── Interval to use per period ─────────────────────────────────────────────────
# IMPORTANT: yfinance "1wk" interval with period="5y" returns ALL history,
# not just 5 years. Use "1d" for all medium/long periods and let the period
# parameter itself limit the data.
CHART_INTERVAL = {
    "1D":  "5m",
    "5D":  "5m",
    "10D": "5m",
    "1M":  "1d",
    "3M":  "1d",
    "6M":  "1d",
    "1Y":  "1d",
    "5Y":  "1d",   # was "1wk" — that caused all history to load
    "10Y": "1d",   # was "1mo"
}


def _normalize_index(series: pd.Series) -> pd.Series:
    if series.index.tz is None:
        series.index = series.index.tz_localize("UTC")
    series.index = series.index.tz_convert(ET)
    return series


def _ticks_from_data(prices_et: pd.DataFrame, n_days: int) -> tuple[list, list]:
    """One tick per trading day, derived from actual data — no generated dates."""
    if prices_et.empty:
        return [], []

    idx = prices_et.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC").tz_convert(ET)

    # Filter to market hours to avoid pre/post-market ghost dates
    mkt = idx[(idx.hour > 9) | ((idx.hour == 9) & (idx.minute >= 30))]
    mkt = mkt[mkt.hour < 16]
    if len(mkt) == 0:
        mkt = idx

    dates_first: dict = {}
    for ts in mkt:
        d = ts.date()
        if d not in dates_first:
            dates_first[d] = ts

    sorted_dates = sorted(dates_first.keys())[-n_days:]
    tick_vals = [dates_first[d] for d in sorted_dates]
    tick_text = [d.strftime("%a %-m/%-d") for d in sorted_dates]
    return tick_vals, tick_text


def _get_xaxis_config(period: str, now_et: datetime, prices_et: pd.DataFrame) -> dict:
    """
    Xaxis config rules:
    - 1D:       rangebreaks for hour + weekend. Hard range 9:30–16:00.
    - 5D/10D:   rangebreaks for weekend only. Ticks from real data.
                NO hour rangebreaks — they truncate 5m data unpredictably.
    - 1M–10Y:   NO rangebreaks at all for daily data — they cause dashed lines.
                Simple dtick/tickformat is enough.
    """

    if period == "1D":
        return dict(
            tickformat="%-I %p",
            dtick=60 * 60 * 1000,
            tickangle=0,
            range=[
                now_et.replace(hour=9,  minute=30, second=0, microsecond=0),
                now_et.replace(hour=16, minute=0,  second=0, microsecond=0),
            ],
            rangebreaks=[
                dict(bounds=["sat", "mon"]),
                dict(bounds=[16, 9.5], pattern="hour"),
            ],
        )

    elif period in ("5D", "10D"):
        n = 5 if period == "5D" else 10
        tick_vals, tick_text = _ticks_from_data(prices_et, n)
        cfg = dict(
            tickvals=tick_vals,
            ticktext=tick_text,
            tickangle=0,
            rangebreaks=[dict(bounds=["sat", "mon"])],
        )
        # Hard x-range: first tick → last data point
        if tick_vals and not prices_et.empty:
            cfg["range"] = [tick_vals[0], prices_et.index[-1]]
        return cfg

    elif period == "1M":
        return dict(
            tickformat="%-m/%-d",
            dtick=7 * 24 * 60 * 60 * 1000,
            tickangle=0,
        )

    elif period == "3M":
        return dict(
            tickformat="%-m/%-d",
            dtick=14 * 24 * 60 * 60 * 1000,
            tickangle=0,
        )

    elif period == "6M":
        return dict(
            tickformat="%b",
            dtick="M1",
            tickangle=0,
        )

    elif period == "1Y":
        return dict(
            tickformat="%b",
            dtick="M1",
            tickangle=0,
        )

    elif period == "5Y":
        return dict(
            tickformat="%Y",
            dtick="M12",
            tickangle=0,
        )

    else:  # 10Y
        return dict(
            tickformat="%Y",
            dtick="M12",
            tickangle=0,
        )


def _prepend_prev_close(series: pd.Series, now_et: datetime) -> pd.Series:
    if series.empty:
        return series
    t_930 = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    if t_930 < series.index[0]:
        return pd.concat([pd.Series([series.iloc[0]], index=[t_930]), series])
    return series


def render_price_chart(tickers: list[str], period: str) -> None:
    st.markdown(
        """
        <style>
            span[data-baseweb="tag"] {
                height: 20px !important; padding: 0 6px !important;
                font-size: 11px !important; border-radius: 4px !important;
            }
            span[data-baseweb="tag"] span { font-size:11px !important; line-height:20px !important; }
            span[data-baseweb="tag"] svg  { width:10px !important; height:10px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_title, col_btn = st.columns([6, 1])
    with col_title:
        label = "Today" if period == "1D" else period
        st.markdown(f"### Price — {label}")
    with col_btn:
        manual_refresh = st.button("↻ Refresh", key="manual_refresh")

    now = datetime.now()
    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = now

    seconds_since = (now - st.session_state["last_refresh"]).total_seconds()
    if manual_refresh or seconds_since >= 300:
        fetch_intraday.clear()
        fetch_prices.clear()
        st.session_state["last_refresh"] = now

    now_et   = datetime.now(ET)
    today_et = now_et.date()
    interval = CHART_INTERVAL[period]

    if period == "1D":
        prices_raw = fetch_intraday(tickers)
    else:
        prices_raw = fetch_prices(tickers, PERIOD_MAP[period], interval=interval)

    last_updated = st.session_state["last_refresh"].strftime("%H:%M:%S")
    st.caption(f"Last updated: {last_updated}  ·  Source: yfinance (~15min delay)")

    if prices_raw.empty:
        st.warning("No data available for the selected tickers and period.")
        return

    # Normalize to ET for tick calculation
    prices_et = prices_raw.copy()
    if prices_et.index.tz is None:
        prices_et.index = prices_et.index.tz_localize("UTC")
    prices_et.index = prices_et.index.tz_convert(ET)

    fig      = go.Figure()
    has_data = False

    for i, ticker in enumerate(tickers):
        if ticker not in prices_raw.columns:
            continue

        color  = COLORS[i % len(COLORS)]
        series = _normalize_index(prices_raw[ticker].dropna().copy())

        if period == "1D":
            series = series[series.index.date == today_et]
            if not series.empty:
                series = _prepend_prev_close(series, now_et)

        if series.empty:
            continue

        has_data = True
        fig.add_trace(go.Scatter(
            x=series.index,
            y=series.values,
            mode="lines",
            name=ticker,
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{ticker}</b><br>%{{x}}<br>$%{{y:.2f}}<extra></extra>",
        ))

    if not has_data:
        st.warning("No data available for the selected tickers and period.")
        return

    xaxis_cfg = _get_xaxis_config(period, now_et, prices_et)

    fig.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8a9abf", size=11),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
        xaxis=dict(
            showgrid=False, zeroline=False, title="",
            tickfont=dict(size=10),
            **xaxis_cfg,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            zeroline=False, title="",
            tickprefix="$", tickfont=dict(size=10),
        ),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    remaining = max(0, 300 - int(seconds_since))
    st.caption(f"Next auto-refresh in {remaining // 60}m {remaining % 60}s")