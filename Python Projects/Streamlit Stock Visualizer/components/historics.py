import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from utils.historics import (
    fetch_historics_data,
    get_visible, get_for_return,
    calc_cumulative_return, calc_daily_return,
    calc_annual_return, calc_monthly_return,
    calc_volatility, calc_correlation,
    calc_moving_averages, calc_optimal_allocation,
    BENCHMARK,
)

COLORS = ["#4f8ef7","#f75f4f","#4fc98e","#f7c74f","#c44fff","#ff914f","#4ff7f0","#f74fa0"]

CHART_INFO = {
    "cumulative":      "📈 **Cumulative Return**\n\nShows growth of $100 invested at period start. Value of 150 = 50% gain. Compared against S&P 500 as benchmark.",
    "return":          "📅 **Return per Period**\n\nDaily return for short periods (1D–1M), monthly for 3M–6M, annual for 1Y+. Green = gain, red = loss.",
    "volatility":      "📊 **Annualized Volatility**\n\nStd deviation of daily returns × √252. Higher = more risk. Growth stocks typically more volatile than blue chips.",
    "correlation":     "🔗 **Correlation Matrix**\n\n+1 = move together, 0 = no relation, -1 = opposite. Low correlation between assets reduces portfolio risk.",
    "moving_avg":      "📉 **Moving Averages (SMA 20 & 200)**\n\nSMA 20 (yellow) = short-term trend. SMA 200 (red) = long-term trend.\nGolden Cross: SMA20 > SMA200 (bullish). Death Cross: SMA20 < SMA200 (bearish).",
    "sharpe":          "⚖️ **Max Sharpe Allocation**\n\nWeights that maximize return per unit of risk. Based on historical data only.",
    "volatility_alloc":"🛡️ **Min Volatility Allocation**\n\nWeights that minimize portfolio volatility. More conservative, prioritizes stability.",
}

LAYOUT = dict(
    height=340, margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#8a9abf", size=11),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(showgrid=False, zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False),
)
LAYOUT_NO_AXES = {k: v for k, v in LAYOUT.items() if k not in ("xaxis","yaxis","legend")}


def _info(key):
    with st.popover("ℹ️"):
        st.markdown(CHART_INFO.get(key, ""))

def _header(title, key):
    c1, c2 = st.columns([10, 1])
    with c1: st.markdown(f"**{title}**")
    with c2: _info(key)

def _plot(fig, key):
    with st.container(border=True):
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)

def _fig():
    f = go.Figure()
    f.update_layout(**LAYOUT)
    return f


# ── 1. CUMULATIVE RETURN ──────────────────────────────────────────────────────
def _chart_cumulative(prices_full: pd.DataFrame, period: str, ticker: str) -> None:
    _header(f"Cumulative Return — {ticker} vs S&P 500", "cumulative")

    # Use for_return so 1D has 2 points (today vs yesterday)
    src  = get_for_return(prices_full, period)
    cols = [c for c in [ticker, BENCHMARK] if c in src.columns]
    data = calc_cumulative_return(src[cols])

    if data.empty:
        st.info("Not enough data for cumulative return chart.")
        return

    fig = _fig()
    for i, col in enumerate(cols):
        fig.add_trace(go.Scatter(
            x=data.index, y=data[col], mode="lines", name=col,
            line=dict(color=COLORS[i] if col != BENCHMARK else "#555e78", width=2),
            hovertemplate=f"<b>{col}</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}}<extra></extra>",
        ))
    _plot(fig, f"cum_{ticker}_{period}")


# ── 2. RETURN PER PERIOD ──────────────────────────────────────────────────────
def _chart_return(prices_full: pd.DataFrame, period: str, ticker: str) -> None:
    src = get_for_return(prices_full, period)
    if ticker not in src.columns:
        return

    SHORT = ("1D", "5D", "10D", "1M")

    if period in SHORT:
        series = calc_daily_return(src[[ticker]])[ticker].dropna()
        label  = "Daily"
        xfmt   = lambda d: d.strftime("%b %d")
    elif period in ("3M", "6M"):
        series = calc_monthly_return(src[[ticker]])[ticker].dropna()
        label  = "Monthly"
        xfmt   = lambda d: d.strftime("%b %Y")
    else:
        series = calc_annual_return(src[[ticker]])[ticker].dropna()
        label  = "Annual"
        xfmt   = lambda d: str(d.year)

    if series.empty:
        _header(f"{label} Return — {ticker}", "return")
        st.info("Not enough data for return chart.")
        return

    _header(f"{label} Return — {ticker}", "return")
    fig = _fig()
    fig.add_trace(go.Bar(
        x=[xfmt(d) for d in series.index],
        y=series.values,
        marker_color=["#4fc98e" if v >= 0 else "#f05a3d" for v in series.values],
        hovertemplate="<b>%{x}</b><br>%{y:.2f}%<extra></extra>",
        name=ticker,
    ))
    fig.update_yaxes(ticksuffix="%")
    _plot(fig, f"ret_{ticker}_{period}")


# ── 3. VOLATILITY ─────────────────────────────────────────────────────────────
def _chart_volatility(prices_full: pd.DataFrame, period: str) -> None:
    src  = get_visible(prices_full, period)
    vol  = calc_volatility(src.drop(columns=[BENCHMARK], errors="ignore"))
    if vol.empty:
        return
    _header("Annualized Volatility (%)", "volatility")
    fig = _fig()
    fig.add_trace(go.Bar(
        x=vol.index.tolist(), y=vol.values,
        marker_color=[COLORS[i % len(COLORS)] for i in range(len(vol))],
        hovertemplate="<b>%{x}</b><br>%{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(ticksuffix="%")
    _plot(fig, f"vol_{period}")


# ── 4. CORRELATION ────────────────────────────────────────────────────────────
def _chart_correlation(prices_full: pd.DataFrame, period: str) -> None:
    src  = get_visible(prices_full, period)
    corr = calc_correlation(src.drop(columns=[BENCHMARK], errors="ignore"))
    if corr.empty:
        st.info("Need ≥ 2 tickers for correlation analysis.")
        return
    _header("Correlation Matrix", "correlation")
    fig = px.imshow(corr, color_continuous_scale="RdBu_r", zmin=-1, zmax=1, text_auto=".2f")
    fig.update_layout(**LAYOUT_NO_AXES, coloraxis_showscale=False)
    fig.update_traces(textfont=dict(size=11))
    _plot(fig, f"corr_{period}")


# ── 5. MOVING AVERAGES ────────────────────────────────────────────────────────
def _chart_moving_avg(prices_full: pd.DataFrame, period: str, ticker: str) -> None:
    vis   = get_visible(prices_full, period)
    ma_df = calc_moving_averages(prices_full, vis, ticker)
    if ma_df.empty:
        return
    _header(f"Moving Averages — {ticker}", "moving_avg")
    fig    = _fig()
    styles = {
        "Price":    dict(color=COLORS[0], width=1.5),
        "SMA 20d":  dict(color="#f7c74f", width=2, dash="dot"),
        "SMA 200d": dict(color="#f75f4f", width=2, dash="dash"),
    }
    for col, style in styles.items():
        if col in ma_df.columns:
            fig.add_trace(go.Scatter(
                x=ma_df.index, y=ma_df[col], mode="lines", name=col,
                line=style,
                hovertemplate=f"<b>{col}</b><br>%{{x|%Y-%m-%d}}<br>${{y:.2f}}<extra></extra>",
            ))
    fig.update_yaxes(tickprefix="$")
    _plot(fig, f"ma_{ticker}_{period}")


# ── 6. ALLOCATION ─────────────────────────────────────────────────────────────
def _chart_allocation(prices_opt: pd.DataFrame, method: str, period: str) -> None:
    title    = "Optimal Allocation — Max Sharpe" if method == "sharpe" else "Optimal Allocation — Min Volatility"
    info_key = "sharpe" if method == "sharpe" else "volatility_alloc"
    _header(title, info_key)

    weights = calc_optimal_allocation(prices_opt, method=method)
    if weights is None or weights.empty:
        n = prices_opt.drop(columns=[BENCHMARK], errors="ignore").shape[1]
        st.info("Need ≥ 2 tickers for optimization." if n < 2 else "Optimization failed.")
        return

    fig = go.Figure(go.Pie(
        labels=weights.index.tolist(), values=weights.values, hole=0.35,
        marker=dict(colors=COLORS[:len(weights)]),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
    ))
    fig.update_layout(**LAYOUT_NO_AXES, showlegend=False)
    _plot(fig, f"alloc_{method}_{period}")


# ── MAIN RENDER ───────────────────────────────────────────────────────────────
def render_historics(tickers: list[str], period: str) -> None:
    st.markdown("### Historicals")
    if not tickers:
        st.info("Select tickers in the sidebar.")
        return

    with st.spinner("Loading historical data..."):
        # Pass tickers as tuple for cache hashability
        prices_full = fetch_historics_data(tuple(tickers), period)
        # For allocation always use at least 1Y
        opt_period  = period if period in ("1Y","5Y","10Y") else "1Y"
        prices_opt  = fetch_historics_data(tuple(tickers), opt_period)

    if prices_full.empty:
        st.warning("No historical data available.")
        return

    # Ticker selector lives in the sidebar (session_state["hist_sel"])
    selected = st.session_state.get("hist_sel", tickers[0])
    if selected not in tickers:
        selected = tickers[0]

    # Row 1
    col1, col2 = st.columns(2)
    with col1: _chart_cumulative(prices_full, period, selected)
    with col2: _chart_return(prices_full, period, selected)

    # Row 2
    col3, col4 = st.columns(2)
    with col3: _chart_volatility(prices_full, period)
    with col4: _chart_correlation(prices_full, period)

    # Row 3
    _chart_moving_avg(prices_full, period, selected)

    # Row 4
    col5, col6 = st.columns(2)
    with col5: _chart_allocation(prices_opt, "sharpe",     period)
    with col6: _chart_allocation(prices_opt, "volatility", period)