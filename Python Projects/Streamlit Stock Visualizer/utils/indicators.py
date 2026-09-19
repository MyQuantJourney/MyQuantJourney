"""
utils/indicators.py
────────────────────
Financial data fetchers used by the Key Indicators card.
All functions that call the yfinance API have a download-based fallback so they
work reliably on Streamlit Cloud (where .info often returns an empty dict).
"""
import pandas as pd
import yfinance as yf
import streamlit as st

# ─── PERIOD → number of data points for sparkline ────────────────────────────
SPARKLINE_PERIODS = {
    "1D":  1,  "5D":  1,  "10D": 1,
    "1M":  1,  "3M":  1,  "6M":  2,
    "1Y":  4,  "5Y":  5,  "10Y": 10,
}


# ─── LOW-LEVEL DOWNLOAD HELPER ────────────────────────────────────────────────
def _yf_download(ticker: str, period: str, interval: str) -> "pd.DataFrame | None":
    """Download via yfinance with fallback for old/new API differences."""
    raw = None
    for kwargs in [{"multi_level_index": False}, {}]:
        try:
            raw = yf.download(
                ticker, period=period, interval=interval,
                auto_adjust=True, progress=False, **kwargs,
            )
            if raw is not None and not raw.empty:
                break
        except TypeError:
            continue
        except Exception:
            return None

    if raw is None or raw.empty:
        return None

    # Flatten MultiIndex columns
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]

    return raw


# ─── TICKER INFO ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_ticker_info(ticker: str) -> dict:
    """
    Fetches .info dict.  Enriches with fast_info if currentPrice is missing.
    Returns an empty dict (never raises) so callers can safely use .get().
    """
    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}
        if not (info.get("currentPrice") or info.get("regularMarketPrice")):
            try:
                fi = t.fast_info
                info.setdefault("currentPrice",  getattr(fi, "last_price",     None))
                info.setdefault("previousClose", getattr(fi, "previous_close", None))
            except Exception:
                pass
        return info
    except Exception:
        return {}


# ─── CURRENT PRICE ────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _price_via_download(ticker: str) -> dict:
    """Fallback: derive current price from last two daily closes."""
    blank = {"price": 0.0, "prev": 0.0, "change": 0.0, "pct": 0.0, "up": True}
    try:
        raw = _yf_download(ticker, "5d", "1d")
        if raw is None or "Close" not in raw.columns:
            return blank
        closes = raw["Close"].dropna()
        if len(closes) >= 2:
            p, q   = float(closes.iloc[-1]), float(closes.iloc[-2])
            change = p - q
            pct    = change / q * 100 if q else 0.0
            return {"price": p, "prev": q, "change": change, "pct": pct, "up": change >= 0}
        if len(closes) == 1:
            return {**blank, "price": float(closes.iloc[0])}
    except Exception:
        pass
    return blank


def get_current_price_data(ticker: str) -> dict:
    """Returns price dict; uses .info then falls back to yf.download."""
    info    = fetch_ticker_info(ticker)
    current = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
    prev    = float(info.get("previousClose") or info.get("regularMarketPreviousClose") or 0)

    if current:
        change = current - prev
        pct    = change / prev * 100 if prev else 0.0
        return {"price": current, "prev": prev, "change": change, "pct": pct, "up": change >= 0}

    return _price_via_download(ticker)


# ─── PE / PB ──────────────────────────────────────────────────────────────────
def get_pe_pb(ticker: str) -> tuple:
    """
    Returns (trailing_pe, price_to_book).
    Falls back to calculated sparkline values if .info is empty.
    """
    info   = fetch_ticker_info(ticker)
    pe_val = info.get("trailingPE")
    pb_val = info.get("priceToBook")

    if not pe_val or not pb_val:
        try:
            fin = fetch_financials(ticker)
            if not pe_val and not fin["pl"].empty:
                pe_val = float(fin["pl"].iloc[-1])
            if not pb_val and not fin["pvp"].empty:
                pb_val = float(fin["pvp"].iloc[-1])
        except Exception:
            pass

    return (pe_val or None, pb_val or None)


# ─── FINANCIALS ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_financials(ticker: str, quarterly: bool = False) -> dict[str, pd.Series]:
    """Fetches historical financials and builds indicator Series."""
    result: dict[str, pd.Series] = {
        "roe":             pd.Series(dtype=float),
        "pl":              pd.Series(dtype=float),
        "revenue":         pd.Series(dtype=float),
        "net_debt_ebitda": pd.Series(dtype=float),
        "pvp":             pd.Series(dtype=float),
        "price":           pd.Series(dtype=float),
    }

    try:
        t = yf.Ticker(ticker)

        income  = t.quarterly_income_stmt  if quarterly else t.income_stmt
        balance = t.quarterly_balance_sheet if quarterly else t.balance_sheet

        def _row(df: pd.DataFrame, *keys) -> pd.Series:
            if df is None or df.empty:
                return pd.Series(dtype=float)
            for k in keys:
                if k in df.index:
                    return df.loc[k].sort_index()
            return pd.Series(dtype=float)

        # Revenue
        rev = _row(income, "Total Revenue", "Revenue", "Net Revenue")
        if not rev.empty:
            result["revenue"] = rev

        # ROE
        ni  = _row(income,  "Net Income", "Net Income Common Stockholders")
        eq  = _row(balance, "Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity")
        if not ni.empty and not eq.empty:
            a, b = ni.align(eq, join="inner")
            roe  = (a / b * 100).replace([float("inf"), float("-inf")], pd.NA)
            result["roe"] = roe.dropna()

        # EBITDA proxy
        eb = _row(income, "EBITDA", "Normalized EBITDA")
        if eb.empty:
            eb = _row(income, "Operating Income", "EBIT")

        # Net Debt / EBITDA
        td  = _row(balance, "Total Debt", "Long Term Debt")
        csh = _row(balance, "Cash And Cash Equivalents",
                   "Cash Cash Equivalents And Short Term Investments")
        if not td.empty and not csh.empty and not eb.empty:
            d, c  = td.align(csh, join="inner")
            nd    = d - c
            nd2, e2 = nd.align(eb, join="inner")
            nde = (nd2 / e2).replace([float("inf"), float("-inf")], pd.NA)
            result["net_debt_ebitda"] = nde.dropna()

        # Price history
        hist = t.history(period="10y", interval="1d", auto_adjust=True)
        if not hist.empty and "Close" in hist.columns:
            price = hist["Close"]
            if price.index.tz is not None:
                price.index = price.index.tz_localize(None)
            result["price"] = price

        # Shares
        sh = _row(balance, "Ordinary Shares Number", "Share Issued")

        # P/L sparkline
        if not ni.empty and not sh.empty and not result["price"].empty:
            a2, s2 = ni.align(sh, join="inner")
            pl_vals = {}
            for dt in a2.index:
                n_v, s_v = a2[dt], s2[dt]
                if pd.isna(n_v) or pd.isna(s_v) or s_v == 0:
                    continue
                eps = n_v / s_v
                px  = result["price"].asof(dt)
                if pd.notna(px) and eps != 0:
                    pl_vals[dt] = px / eps
            if pl_vals:
                result["pl"] = pd.Series(pl_vals).sort_index()

        # P/VP sparkline
        if not eq.empty and not sh.empty and not result["price"].empty:
            a3, s3 = eq.align(sh, join="inner")
            pvp_vals = {}
            for dt in a3.index:
                e_v, s_v = a3[dt], s3[dt]
                if pd.isna(e_v) or pd.isna(s_v) or s_v == 0:
                    continue
                bvps = e_v / s_v
                px   = result["price"].asof(dt)
                if pd.notna(px) and bvps != 0:
                    pvp_vals[dt] = px / bvps
            if pvp_vals:
                result["pvp"] = pd.Series(pvp_vals).sort_index()

    except Exception:
        pass

    return result


# ─── SLICE SPARKLINE ─────────────────────────────────────────────────────────
def slice_sparkline(series: pd.Series, period: str, quarterly: bool) -> pd.Series:
    if series.empty:
        return series
    n = SPARKLINE_PERIODS.get(period, 1)
    if not quarterly:
        n = max(n, 2) if period not in ("1D", "5D", "10D", "1M", "3M") else 1
    sliced = series.sort_index().tail(n)
    return sliced if len(sliced) >= 2 else pd.Series(dtype=float)