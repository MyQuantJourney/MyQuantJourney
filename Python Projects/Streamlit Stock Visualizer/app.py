import streamlit as st
from components.sidebar import render_sidebar
from components.price_chart import render_price_chart
from components.indicators_card import render_indicators
from components.historics import render_historics

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── GLOBAL CSS ──────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* Reduce main content side padding */
        .block-container {
            padding-top: 2rem !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
        }
        h1 { margin-top: 0 !important; padding-top: 0 !important; }

        /* Tighten gap between indicator card columns */
        [data-testid="stHorizontalBlock"] {
            gap: 0.5rem !important;
        }

        /* Reduce inner padding of each st.container(border=True) card */
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 0.5rem !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
selected_tickers, selected_period = render_sidebar()

# ─── MAIN CONTENT ─────────────────────────────────────────────────────────────

if not selected_tickers:
    st.info("👈 Select at least one ticker in the sidebar to get started.")
else:
    # Price chart
    render_price_chart(selected_tickers, selected_period)

    st.divider()

    # Key indicators — quarterly toggle is handled inside the component
    render_indicators(
        tickers=selected_tickers,
        period=selected_period,
        quarterly=False,   # default; overridden by the toggle inside the component
    )

    st.divider()

    render_historics(
        tickers=selected_tickers,
        period=selected_period,
    )