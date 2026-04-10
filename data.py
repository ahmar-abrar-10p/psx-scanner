import functools
import pandas as pd
import pandas_ta as ta
import requests
from pathlib import Path
import logging

from ohlcv_store import (
    _last_psx_trading_day,
    _make_session,
    update_single,
)

logger = logging.getLogger(__name__)

UNIVERSE_FILE = Path(__file__).parent / "KMI_all.csv"

# Sarmaaya API endpoints for live PSX data
SARMAAYA_STOCKS_URL = "https://beta-restapi.sarmaaya.pk/api/stocks/"
SARMAAYA_TICKER_URL = "https://beta-restapi.sarmaaya.pk/api/stocks/ticker"


@functools.lru_cache(maxsize=1)
def _load_universe_df() -> pd.DataFrame:
    """Load and cache the universe CSV. Called once per process."""
    return pd.read_csv(UNIVERSE_FILE)


def load_universe() -> list[str]:
    """Load all KMI Shariah stock symbols from CSV."""
    return _load_universe_df()["symbol"].tolist()


def get_company_info(symbol: str) -> tuple[str, str]:
    """Look up company name and sector from KMI_all.csv. Returns (name, sector)."""
    df = _load_universe_df()
    match = df[df["symbol"] == symbol]
    if not match.empty:
        name = str(match.iloc[0].get("name", symbol))
        sector = str(match.iloc[0].get("sector", "Unknown"))
        return name, sector
    return symbol, "Unknown"


def fetch_live_data(progress_callback=None) -> dict[str, dict]:
    """
    Fetch today's live OHLCV for all PSX stocks from Sarmaaya API.
    Combines two endpoints in parallel:
      - /api/stocks/       -> open, high, low, close, change
      - /api/stocks/ticker -> volume
    Returns dict keyed by symbol: {symbol: {open, high, low, close, volume, change}}.
    Returns empty dict on failure.
    """
    from concurrent.futures import ThreadPoolExecutor

    if progress_callback:
        progress_callback("Fetching live data from Sarmaaya API...", 0, 0)

    # Fetch both endpoints in parallel
    def _get(url):
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_stocks = ex.submit(_get, SARMAAYA_STOCKS_URL)
        f_ticker = ex.submit(_get, SARMAAYA_TICKER_URL)

    try:
        stocks_data = f_stocks.result()
    except Exception as e:
        logger.warning("Sarmaaya /api/stocks/ failed: %s", e)
        return {}

    items = stocks_data if isinstance(stocks_data, list) else stocks_data.get("response", [])

    # Build OHLC lookup
    data = {}
    for item in items:
        sym = item.get("symbol", "").strip()
        if not sym:
            continue
        try:
            data[sym] = {
                "open": float(item.get("open", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "close": float(item.get("close", 0)),
                "change": float(item.get("change", 0)),
                "volume": 0,
            }
        except (ValueError, TypeError):
            continue

    # Merge volume from ticker endpoint
    try:
        ticker_data = f_ticker.result()
    except Exception as e:
        logger.warning("Sarmaaya /api/stocks/ticker failed: %s", e)
        return data

    ticker_items = ticker_data if isinstance(ticker_data, list) else ticker_data.get("response", [])
    for item in ticker_items:
        sym = item.get("symbol", "").strip()
        if sym in data:
            try:
                data[sym]["volume"] = int(float(item.get("volume", 0)))
            except (ValueError, TypeError):
                pass

    logger.info("Sarmaaya API: fetched %d stocks with OHLCV", len(data))
    return data



def fetch_ohlcv(symbol: str, session=None) -> pd.DataFrame | None:
    """Fetch OHLCV for a single PSX ticker using the persistent OHLCV store."""
    return update_single(symbol, session=session)


def compute_technicals(df: pd.DataFrame) -> dict:
    """
    Compute technical indicators on OHLCV data.
    Returns a flat dict of the latest values — ready to pass to CrewAI agents.
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # RSI (14)
    rsi = ta.rsi(close, length=14)

    # EMA (20, 50)
    ema20 = ta.ema(close, length=20)
    ema50 = ta.ema(close, length=50)

    # MACD
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)

    # Average True Range — for stoploss calculation
    atr = ta.atr(high, low, close, length=14)

    # Volume trend: today's volume vs 20-day average
    vol_avg20 = volume.rolling(20).mean()
    vol_ratio = (volume / vol_avg20).iloc[-1]

    # 52-week high/low from available data
    week52_high = high.max()
    week52_low = low.min()

    # Date of the most recent bar — critical for freshness checks.
    # yfinance's PSX feed lags by 1+ trading days fairly often.
    last_idx = df.index[-1]
    last_bar_date = last_idx.date().isoformat() if hasattr(last_idx, "date") else str(last_idx)[:10]

    latest = {
        "last_bar_date": last_bar_date,
        "price": round(float(close.iloc[-1]), 2),
        "rsi14": round(float(rsi.iloc[-1]), 2) if rsi is not None else None,
        "ema20": round(float(ema20.iloc[-1]), 2) if ema20 is not None else None,
        "ema50": round(float(ema50.iloc[-1]), 2) if ema50 is not None else None,
        "macd": round(float(macd_df["MACD_12_26_9"].iloc[-1]), 4) if macd_df is not None else None,
        "macd_signal": round(float(macd_df["MACDs_12_26_9"].iloc[-1]), 4) if macd_df is not None else None,
        "macd_hist": round(float(macd_df["MACDh_12_26_9"].iloc[-1]), 4) if macd_df is not None else None,
        "atr14": round(float(atr.iloc[-1]), 2) if atr is not None else None,
        "volume": int(volume.iloc[-1]),
        "volume_ratio": round(float(vol_ratio), 2),  # >1 means above average volume
        "week52_high": round(float(week52_high), 2),
        "week52_low": round(float(week52_low), 2),
        "price_vs_ema20": round((float(close.iloc[-1]) - float(ema20.iloc[-1])) / float(ema20.iloc[-1]) * 100, 2) if ema20 is not None else None,
        "price_vs_ema50": round((float(close.iloc[-1]) - float(ema50.iloc[-1])) / float(ema50.iloc[-1]) * 100, 2) if ema50 is not None else None,
    }

    return latest


def fetch_all(progress_callback=None) -> list[dict]:
    """
    Load OHLCV from the local store and compute technicals for all stocks.
    Returns list of dicts — one per stock — ready for CrewAI agents.

    No network calls — reads entirely from the OHLCV store (cache/ohlcv/).
    Use 'Generate History' to backfill and 'Refresh Today' to update live data.

    progress_callback: optional function(msg, current, total) for UI progress updates.
    """
    from ohlcv_store import load_ohlcv

    symbols = load_universe()
    results = []
    total = len(symbols)

    if progress_callback:
        progress_callback(f"Loading OHLCV store for {total} stocks...", 0, total)

    skipped = []
    for i, symbol in enumerate(symbols):
        try:
            df = load_ohlcv(symbol)
            if df is None or df.empty:
                skipped.append((symbol, "not in OHLCV store"))
                continue

            if len(df) < 20:
                skipped.append((symbol, f"insufficient data ({len(df)} rows)"))
                continue

            technicals = compute_technicals(df)
            technicals["symbol"] = symbol
            results.append(technicals)

            if progress_callback and (i + 1) % 50 == 0:
                progress_callback(f"Computed {i + 1}/{total} ({len(results)} OK)", i + 1, total)

        except Exception as e:
            skipped.append((symbol, str(e)[:80]))
            continue

    if not results:
        if progress_callback:
            progress_callback(
                "[ERROR] No OHLCV data available. Click 'Generate History' to backfill.",
                0, total,
            )
        return []

    if skipped and progress_callback:
        progress_callback(f"[SKIP] {len(skipped)} symbols had no data: {', '.join(s for s, _ in skipped[:10])}{'...' if len(skipped) > 10 else ''}", len(results), total)

    # Freshness check
    bar_dates = [r["last_bar_date"] for r in results if r.get("last_bar_date")]
    if bar_dates:
        data_as_of = max(bar_dates)
        expected = _last_psx_trading_day().isoformat()
        if data_as_of < expected and progress_callback:
            progress_callback(
                f"[STALE] Data as of {data_as_of}, expected {expected}. "
                f"Click 'Refresh Today' to update.",
                len(results), total,
            )
        elif progress_callback:
            progress_callback(f"[OK] {len(results)} stocks ready, data as of {data_as_of}", len(results), total)

    return results


def fetch_single_stock(symbol: str, progress_callback=None) -> tuple[pd.DataFrame | None, dict | None]:
    """
    Load OHLCV for a single stock from the persistent store.
    Returns (DataFrame with OHLCV, live_bar dict built from stored data).
    Returns (None, None) if data is unavailable.
    """
    from ohlcv_store import load_ohlcv

    if progress_callback:
        progress_callback("fetch", f"Loading history for {symbol} from OHLCV store...")

    df = load_ohlcv(symbol)

    if df is None or df.empty:
        if progress_callback:
            progress_callback("fetch", f"[ERROR] No data for {symbol}. Run 'Generate History' first.")
        return None, None

    if progress_callback:
        progress_callback("fetch", f"Got {len(df)} bars ({df.index[0].date()} to {df.index[-1].date()})")

    # Build live_bar from the latest row in the store
    last = df.iloc[-1]
    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else float(last["Close"])
    change = round(float(last["Close"]) - prev_close, 2)

    live_bar = {
        "open": float(last["Open"]),
        "high": float(last["High"]),
        "low": float(last["Low"]),
        "close": float(last["Close"]),
        "volume": int(last["Volume"]),
        "ldcp": prev_close,
        "change": change,
    }

    return df, live_bar


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    symbols = load_universe()
    print(f"Universe loaded: {len(symbols)} stocks")
    print(f"First 5: {symbols[:5]}")
    print("\nFetching data for first 3 stocks...\n")

    session = _make_session()
    for symbol in symbols[:3]:
        df = fetch_ohlcv(symbol, session)
        if df is None:
            print(f"{symbol}: No data")
            continue
        tech = compute_technicals(df)
        tech["symbol"] = symbol
        print(f"{symbol}: price={tech['price']} RSI={tech['rsi14']} EMA20={tech['ema20']} vol_ratio={tech['volume_ratio']}")
