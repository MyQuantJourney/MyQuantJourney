# Stock Dashboard

## Project Structure

```
dashboard/
│
├── app.py                  # Entry point — page config + layout
│
├── components/             # UI components (one file per section)
│   ├── __init__.py
│   ├── sidebar.py          # Logo, ticker selector, period buttons, best/worst
│   └── price_chart.py      # Intraday price chart with auto-refresh
│
├── utils/                  # Shared logic
│   ├── __init__.py
│   └── data.py             # yfinance fetchers, CSV loader, best/worst calc
│
├── data/
│   └── sp500.csv           # S&P 500 ticker list (Symbol, Name, Sector, ...)
│
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## CSV Format

The `data/sp500.csv` file must contain at minimum a column named `Symbol` or `Ticker`.
Additional columns (Name, Sector, etc.) are loaded but not required.
