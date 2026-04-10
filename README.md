# PSX AI Scanner

A Python + Streamlit app that scans all Shariah-compliant stocks on the Pakistan Stock Exchange (PSX) and generates top 10 T+1 and swing trade picks with entry, target, stoploss, and risk:reward -- powered by AI analysis on real market data.

## How It Works

1. **Generate History** -- downloads 6 months of OHLCV history for all KMI stocks from Yahoo Finance (one-time setup)
2. **Refresh Today** -- fetches today's live prices from Sarmaaya API and updates the local store
3. **Scan** -- reads from local OHLCV store (no network calls), computes technical indicators, and passes data to two CrewAI agents:
   - **Analyst** -- analyzes all stocks and ranks by confluence score
   - **Strategist** -- picks top 10 and generates complete trade plans with exact price levels
4. **Stock Analyzer** -- deep 17-technique analysis on any individual stock with AI verdict

AI never fetches or invents price data -- all numbers come from real market data stored locally.

## Stack

- Python 3.12
- Streamlit -- UI
- CrewAI -- agent orchestration
- LLM providers: Gemini, Groq, OpenAI, Ollama (configurable)
- pandas + pandas-ta -- technical analysis
- yfinance -- historical OHLCV backfill
- Sarmaaya API -- live PSX prices (OHLC + volume)

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

**5. First run:**
- Click **Generate History** in the sidebar to download 6 months of stock data
- Click **Refresh Today** to fetch today's live prices
- Then click **Scan** to run the AI analysis

## Data Architecture

```
cache/ohlcv/           -- per-stock parquet files (OGDC.parquet, MEBL.parquet, ...)
                          6 months initial, grows daily, max 1 year retention
```

- **History**: stored locally in `cache/ohlcv/`, one parquet per stock
- **Daily updates**: "Refresh Today" fetches live OHLCV from Sarmaaya API and appends to store
- **Scans read locally**: no network calls during scan -- pure local computation
- **Rebuild**: "Generate/Rebuild History" deletes all and re-fetches 6 months from yfinance

## Stock Universe

`KMI_all.csv` -- all Shariah-compliant stocks from the KMI All Shares index (after sector/symbol exclusions), sorted by market cap. Enriched with company names from Sarmaaya API and sectors from PSX.

To regenerate the list, export a fresh `KMIALLSHR.csv` from the PSX website and run:
```bash
python parse_kmi.py
```

## File Structure

```
psx_scanner/
├── app.py              # Streamlit entry point (multi-page navigation)
├── pages/
│   ├── 0_KMI_Scanner.py   # Full scan UI (Generate History, Refresh Today, Scan)
│   └── 1_Stock_Analyzer.py # Single stock deep analysis UI
├── scanner.py          # Scan pipeline orchestrator
├── agents.py           # CrewAI agent definitions (Analyst + Strategist)
├── analyzer.py         # Single stock deep analysis (17 techniques)
├── data.py             # OHLCV loading, technicals computation, live data API
├── ohlcv_store.py      # Persistent OHLCV store (parquet per stock)
├── parse_kmi.py        # Build KMI_all.csv from KMIALLSHR.csv + enrichment sources
├── KMI_all.csv         # Stock universe (ships with code)
├── KMIALLSHR.csv       # Raw PSX index export (source for parse_kmi.py)
├── .env                # API keys
└── requirements.txt
```

## Features

- All KMI Shariah-compliant stocks (200+)
- Top 10 trade picks with buy range, target 1, target 2, stoploss, R:R
- Trade style: T+1 or Swing 3-5 days
- Risk level: Conservative, Moderate, Aggressive
- Multiple AI providers: Gemini, Groq, OpenAI, Ollama
- Single stock deep analyzer with 17 technical techniques + AI verdict
- WhatsApp-ready share format
- Persistent local OHLCV store -- fast scans with no repeated downloads

## Disclaimer

This tool is for informational purposes only. Not financial advice. Always do your own research before trading.
