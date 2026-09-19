import numpy as np
import pandas as pd
import streamlit as st

from utils.data import _download_single

BENCHMARK = "^GSPC"

# Trading rows to show per period
PERIOD_ROWS = {
    "1D": 1, "5D": 5, "10D": 10, "1M": 21,
    "3M": 63, "6M": 126, "1Y": 252, "5Y": 1260, "10Y": 2520,
}

# Extra rows to fetch for SMA 200 warmup
PERIOD_FETCH = {
    "1D": 22, "5D": 26, "10D": 31, "1M": 42,
    "3M": 84, "6M": 147, "1Y": 473, "5Y": 1481, "10Y": 2741,
}

# yfinance period strings that cover PERIOD_FETCH rows
FETCH_YF_PERIOD = {
    "1D": "1mo", "5D": "1mo", "10D": "3mo", "1M": "3mo",
    "3M": "6mo", "6M": "1y", "1Y": "2y", "5Y": "7y", "10Y": "max",
}


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize index to date-only (no time, no tz), deduplicate, sort."""
    if df.empty:
        return df
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    # Group by calendar date to collapse any intraday timestamps into one row per day
    df.index = idx
    df.index = df.index.date  # pure date objects — no time component
    df.index = pd.to_datetime(df.index)  # back to datetime for pandas ops
    df = df.groupby(df.index).last()
    df = df.sort_index()
    return df


@st.cache_data(ttl=3600)
def fetch_historics_data(tickers: tuple, period: str) -> pd.DataFrame:
    """
    Fetches daily price history for tickers + benchmark.
    Returns a clean DataFrame with date-only index, no duplicates.
    Fetches extra rows for SMA 200 warmup.
    tickers must be a tuple (hashable for cache).
    """
    all_tickers = list(dict.fromkeys(list(tickers) + [BENCHMARK]))
    yf_period   = FETCH_YF_PERIOD.get(period, "2y")

    series_list = [
        s for t in all_tickers
        if (s := _download_single(t, period=yf_period, interval="1d")) is not None
        and not s.empty
    ]
    if not series_list:
        return pd.DataFrame()

    df = pd.concat(series_list, axis=1).dropna(how="all")
    return _clean(df)


def get_visible(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Returns the last N trading rows for the selected period."""
    if df.empty:
        return df
    return df.tail(PERIOD_ROWS.get(period, 252))


def get_for_return(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Returns visible + 1 extra row so pct_change has a reference point."""
    if df.empty:
        return df
    n = PERIOD_ROWS.get(period, 252) + 1
    return df.tail(n)


# ─── CALCULATIONS ─────────────────────────────────────────────────────────────

def calc_cumulative_return(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or len(prices) < 2:
        return pd.DataFrame()
    return (prices / prices.iloc[0]) * 100


def calc_daily_return(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    return prices.pct_change().dropna() * 100


def calc_annual_return(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    return prices.resample("YE").last().pct_change().dropna(how="all") * 100


def calc_monthly_return(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    return prices.resample("ME").last().pct_change().dropna(how="all") * 100


def calc_volatility(prices: pd.DataFrame) -> pd.Series:
    if prices.empty:
        return pd.Series(dtype=float)
    return (prices.pct_change().dropna().std() * np.sqrt(252) * 100).round(2)


def calc_correlation(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or prices.shape[1] < 2:
        return pd.DataFrame()
    return prices.pct_change().dropna().corr().round(3)


def calc_moving_averages(prices_full: pd.DataFrame, prices_visible: pd.DataFrame,
                         ticker: str, short: int = 20, long: int = 200) -> pd.DataFrame:
    if prices_full.empty or ticker not in prices_full.columns:
        return pd.DataFrame()
    # Always clean to ensure daily deduplicated index
    pf = _clean(prices_full[[ticker]])
    pv = _clean(prices_visible[[ticker]]) if not prices_visible.empty else prices_visible
    s  = pf[ticker].dropna()
    df = pd.DataFrame({
        "Price":          s,
        f"SMA {short}d":  s.rolling(short).mean(),
        f"SMA {long}d":   s.rolling(long).mean(),
    })
    if not pv.empty:
        df = df[df.index >= pv.index[0]]
    return df.dropna(subset=["Price"])


def calc_optimal_allocation(prices: pd.DataFrame, method: str = "sharpe"):
    stock = prices.drop(columns=[BENCHMARK], errors="ignore")
    if stock.empty or stock.shape[1] < 2:
        return None
    try:
        from pypfopt.efficient_frontier import EfficientFrontier
        from pypfopt.expected_returns import mean_historical_return
        from pypfopt.risk_models import sample_cov
        mu = mean_historical_return(stock)
        S  = sample_cov(stock)
        ef = EfficientFrontier(mu, S)
        ef.max_sharpe() if method == "sharpe" else ef.min_volatility()
        w = ef.clean_weights()
        return pd.Series({k: v for k, v in w.items() if v > 0.001})
    except Exception:
        return None