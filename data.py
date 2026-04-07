import pandas as pd
import pandas_ta as ta
import yfinance as yf
from curl_cffi import requests as curl_requests
from pathlib import Path

UNIVERSE_FILE = Path(__file__).parent / "KMI_top100.csv"
LOOKBACK_DAYS = "60d"  # enough history for EMA(50) and RSI(14)


def load_universe() -> list[str]:
    """Load top 100 KMI Shariah stock symbols from CSV."""
    df = pd.read_csv(UNIVERSE_FILE)
    return df["symbol"].tolist()


def fetch_ohlcv(symbol: str, session) -> pd.DataFrame | None:
    """
    Fetch OHLCV data for a single PSX ticker via yfinance.
    Uses .KA suffix (Karachi) and a curl_cffi session to bypass Windows SSL issues.
    Returns None if data is unavailable or empty.
    """
    ticker = yf.Ticker(f"{symbol}.KA", session=session)
    df = ticker.history(period=LOOKBACK_DAYS, interval="1d")
    if df.empty:
        return None
    df.index = pd.to_datetime(df.index)
    return df[["Open", "High", "Low", "Close", "Volume"]]


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

    latest = {
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
    Fetch OHLCV and compute technicals for all stocks in the universe.
    Returns list of dicts — one per stock — ready for CrewAI agents.

    progress_callback: optional function(symbol, current, total) for UI progress updates.
    """
    symbols = load_universe()
    session = curl_requests.Session(verify=False)
    results = []
    total = len(symbols)

    for i, symbol in enumerate(symbols):
        if progress_callback:
            progress_callback(symbol, i + 1, total)

        try:
            df = fetch_ohlcv(symbol, session)
            if df is None or len(df) < 20:
                # Not enough data for indicators
                continue
            technicals = compute_technicals(df)
            technicals["symbol"] = symbol
            results.append(technicals)
        except Exception as e:
            # Skip stocks that fail — don't crash the whole scan
            print(f"[SKIP] {symbol}: {e}")
            continue

    return results


if __name__ == "__main__":
    # Quick test: fetch first 5 stocks and print results
    symbols = load_universe()
    print(f"Universe loaded: {len(symbols)} stocks")
    print(f"First 5: {symbols[:5]}")
    print("\nFetching data for first 3 stocks...\n")

    session = curl_requests.Session(verify=False)
    for symbol in symbols[:3]:
        df = fetch_ohlcv(symbol, session)
        if df is None:
            print(f"{symbol}: No data")
            continue
        tech = compute_technicals(df)
        tech["symbol"] = symbol
        print(f"{symbol}: price={tech['price']} RSI={tech['rsi14']} EMA20={tech['ema20']} vol_ratio={tech['volume_ratio']}")
