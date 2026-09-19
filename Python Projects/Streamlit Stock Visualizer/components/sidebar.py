import streamlit as st
from utils.data import load_tickers, fetch_prices, best_worst, PERIOD_MAP

# ─── PERIOD BUTTON ROWS ───────────────────────────────────────────────────────
# Groups the period labels into rows of 3 for the grid layout
PERIOD_ROWS = [
    ["1D",  "5D",  "10D"],
    ["1M",  "3M",  "6M"],
    ["1Y",  "5Y",  "10Y"],
]


def render_sidebar() -> tuple[list[str], str]:
    """
    Renders the full sidebar:
      - Logo
      - Ticker multiselect (loaded from CSV)
      - Period selector (compact button grid)
      - Best / Worst stock cards

    Returns:
        selected_tickers (list[str]): tickers chosen by the user
        selected_period  (str):       active period label, e.g. "1M"
    """
    with st.sidebar:

        # ── Logo ─────────────────────────────────────────────────────────────
        st.markdown("## 📈 Stock Analysis")
        st.divider()

        # ── Ticker selector ───────────────────────────────────────────────────
        st.markdown("**Tickers**")

        sp500_df = load_tickers("data/sp500.csv")
        all_tickers = sp500_df["Ticker"].tolist()

        # Default to first two available tickers
        default = [t for t in ["AAPL", "MSFT"] if t in all_tickers] or all_tickers[:2]

        selected_tickers: list[str] = st.multiselect(
            label="Tickers",
            options=all_tickers,
            default=default,
            placeholder="Search ticker...",
            label_visibility="collapsed",
        )

        # ── Period selector ───────────────────────────────────────────────────
        # Compact CSS to reduce button size and spacing
        st.markdown(
            """
            <style>
                /* Shrink sidebar buttons */
                section[data-testid="stSidebar"] .stButton > button {
                    padding: 2px 4px !important;
                    font-size: 11px !important;
                    min-height: 0 !important;
                    height: 26px !important;
                    line-height: 1 !important;
                }
                /* Reduce gaps between sidebar elements */
                section[data-testid="stSidebar"] .block-container {
                    gap: 0 !important;
                }
                section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
                    gap: 4px !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "<p style='margin:16px 0 20px;font-size:14px;font-weight:600;'>Period</p>",
            unsafe_allow_html=True,
        )

        # Initialize period in session state
        if "period" not in st.session_state:
            st.session_state["period"] = "1M"

        # Render 3×3 button grid
        for row in PERIOD_ROWS:
            cols = st.columns(3)
            for col, period in zip(cols, row):
                with col:
                    is_active = st.session_state["period"] == period
                    if st.button(
                        period,
                        key=f"period_{period}",
                        type="primary" if is_active else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["period"] = period
                        st.rerun()

        selected_period: str = st.session_state["period"]

        # ── Viewing Ticker selector ───────────────────────────────────────────
        st.markdown(
            "<p style='margin:20px 0 20px;font-size:14px;font-weight:600;'>Viewing Ticker</p>",
            unsafe_allow_html=True,
        )

        if selected_tickers:
            if "hist_sel" not in st.session_state or st.session_state["hist_sel"] not in selected_tickers:
                st.session_state["hist_sel"] = selected_tickers[0]

            st.selectbox(
                "viewing_ticker",
                options=selected_tickers,
                key="hist_sel",
                label_visibility="collapsed",
            )
        else:
            st.markdown(
                "<p style='font-size:12px;color:#5a6a90;'>No tickers selected</p>",
                unsafe_allow_html=True,
            )

    return selected_tickers, selected_period