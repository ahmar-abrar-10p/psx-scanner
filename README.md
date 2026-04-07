# PSX AI Scanner

A local Python app that scans the top 100 Shariah-compliant stocks on the Pakistan Stock Exchange (PSX) and generates top 10 T+1 and swing trade picks with entry, target, stoploss, and risk:reward — powered by AI analysis on real market data.

## How It Works

1. Loads top 100 stocks from KMI All Shares index (Shariah compliant)
2. Fetches end-of-day OHLCV data via yfinance
3. Computes technical indicators (RSI, EMA, MACD, ATR, volume) using pandas-ta
4. Passes computed data to two CrewAI agents:
   - **Analyst** — screens and shortlists technically strong setups
   - **Strategist** — generates complete trade plans with exact price levels
5. Displays results in a Streamlit web UI

AI never fetches or invents price data — all numbers come from real market data.

## Stack

- Python 3.12
- Streamlit — UI
- CrewAI — agent orchestration
- Google Gemini (gemini-2.0-flash) — LLM
- pandas + pandas-ta — technical analysis
- yfinance — OHLCV data

## Setup

**1. Clone the repo:**
```bash
git clone https://github.com/ahmar-abrar-10p/psx-scanner.git
cd psx-scanner
```

**2. Install dependencies:**
```bash
pip install -r requirements.txt
```

**3. Add your API key:**

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=NA
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).

**4. Run the app:**
```bash
python -m streamlit run app.py
```

## Stock Universe

The scanner uses `KMI_top100.csv` — top 100 Shariah-compliant stocks from the KMI All Shares index, sorted by market cap. This list is static and should be refreshed every ~6 months when PSX recomposes the index.

To regenerate the list, export a fresh `KMIALLSHR.csv` from the PSX website and run:
```bash
python parse_kmi.py
```

## Features

- Top 10 trade picks with buy range, target 1, target 2, stoploss, R:R
- Trade style: T+1 or Swing 3-5 days
- Risk level: Conservative, Moderate, Aggressive
- Configurable AI provider (Gemini / OpenAI)
- WhatsApp-ready share format

## Disclaimer

This tool is for informational purposes only. Not financial advice. Always do your own research before trading.
