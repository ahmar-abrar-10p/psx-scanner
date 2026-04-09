import pandas as pd
import pandas_ta as ta
import yfinance as yf
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, date
import requests as std_requests
import time
import logging

logger = logging.getLogger(__name__)

UNIVERSE_FILE = Path(__file__).parent / "KMI_top100.csv"
CACHE_DIR = Path(__file__).parent / "cache"
META_SUFFIX = ".meta.json"
LOOKBACK_DAYS = "60d"  # enough history for EMA(50) and RSI(14)
FETCH_DELAY = 1.0  # seconds between requests to avoid rate limiting
PSX_MARKET_WATCH_URL = "https://dps.psx.com.pk/market-watch"


def _last_psx_trading_day(today: date | None = None) -> date:
    """Most recent PSX trading day (Mon-Fri) on or before `today`.
    PSX is closed Sat/Sun. Does not account for public holidays."""
    d = today or date.today()
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d = date.fromordinal(d.toordinal() - 1)
    return d


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _cache_path(date_str: str | None = None) -> Path:
    """Path to the parquet cache file for a given date (defaults to today)."""
    date_str = date_str or _today_str()
    return CACHE_DIR / f"technicals_{date_str}.parquet"


def cache_exists(date_str: str | None = None) -> bool:
    return _cache_path(date_str).exists()


def _meta_path(date_str: str | None = None) -> Path:
    return _cache_path(date_str).with_suffix(_cache_path(date_str).suffix + META_SUFFIX)


def cache_info(date_str: str | None = None) -> dict | None:
    """Return metadata about the cached file for the given date, or None.
    Includes `data_as_of` (max last-bar date across tickers) and `is_stale` flag."""
    p = _cache_path(date_str)
    if not p.exists():
        return None
    stat = p.stat()
    df = pd.read_parquet(p)
    data_as_of = None
    if "last_bar_date" in df.columns and not df["last_bar_date"].isna().all():
        data_as_of = str(df["last_bar_date"].max())
    expected = _last_psx_trading_day().isoformat()
    return {
        "path": str(p),
        "date": date_str or _today_str(),
        "rows": len(df),
        "saved_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "data_as_of": data_as_of,
        "expected_trading_day": expected,
        "is_stale": bool(data_as_of and data_as_of < expected),
    }


def _save_cache(records: list[dict], date_str: str | None = None) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(_cache_path(date_str), index=False)


def _load_cache(date_str: str | None = None) -> list[dict]:
    return pd.read_parquet(_cache_path(date_str)).to_dict(orient="records")


def load_universe() -> list[str]:
    """Load top 100 KMI Shariah stock symbols from CSV."""
    df = pd.read_csv(UNIVERSE_FILE)
    return df["symbol"].tolist()


def _make_session():
    """curl_cffi session with chrome impersonation — required for Yahoo crumb flow."""
    return curl_requests.Session(verify=False, impersonate="chrome")


def fetch_psx_live() -> dict[str, dict]:
    """
    Scrape dps.psx.com.pk/market-watch for same-day OHLCV of all listed stocks.
    Returns dict keyed by symbol: {symbol: {open, high, low, close, volume, ldcp, change}}.
    Returns empty dict on failure.
    """
    try:
        r = std_requests.get(
            PSX_MARKET_WATCH_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            verify=False,
            timeout=20,
        )
        r.raise_for_status()
    except Exception as e:
        logger.warning("PSX market-watch fetch failed: %s", e)
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("tbody.tbl__body tr")
    if not rows:
        logger.warning("PSX market-watch: no rows found in HTML")
        return {}

    data = {}
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 11:
            continue
        symbol = cells[0].get("data-search", "").strip()
        if not symbol:
            continue
        try:
            data[symbol] = {
                "open": float(cells[4].get("data-order", 0)),
                "high": float(cells[5].get("data-order", 0)),
                "low": float(cells[6].get("data-order", 0)),
                "close": float(cells[7].get("data-order", 0)),
                "volume": int(float(cells[10].get("data-order", 0))),
                "ldcp": float(cells[3].get("data-order", 0)),
                "change": float(cells[8].get("data-order", 0)),
            }
        except (ValueError, TypeError):
            continue

    logger.info("PSX market-watch: fetched %d stocks", len(data))
    return data


def _append_live_bar(hist_df: pd.DataFrame, live: dict, today: date) -> pd.DataFrame:
    """
    Append today's live bar from PSX to a historical yfinance DataFrame.
    If the last bar in hist_df is already today, replace it with the live data.
    """
    today_ts = pd.Timestamp(today)
    live_row = pd.DataFrame(
        [{
            "Open": live["open"],
            "High": live["high"],
            "Low": live["low"],
            "Close": live["close"],
            "Volume": live["volume"],
        }],
        index=pd.DatetimeIndex([today_ts]),
    )

    if not hist_df.empty and hist_df.index[-1].date() >= today:
        # Replace the stale/partial last bar
        hist_df = hist_df[hist_df.index.date < today]

    return pd.concat([hist_df, live_row])


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


def fetch_all(progress_callback=None, force_refresh: bool = False) -> list[dict]:
    """
    Fetch OHLCV and compute technicals for all stocks in the universe.
    Returns list of dicts — one per stock — ready for CrewAI agents.

    Caches results to a date-stamped parquet file. On subsequent calls the same day,
    returns the cached data unless force_refresh=True.

    progress_callback: optional function(symbol, current, total) for UI progress updates.
    force_refresh: if True, ignore today's cache and re-fetch from yfinance.
    """
    # Try cache first
    if not force_refresh and cache_exists():
        cached = _load_cache()
        if progress_callback:
            info = cache_info()
            progress_callback(
                f"[CACHE] Loaded {len(cached)} stocks from cache (saved {info['saved_at']})",
                len(cached),
                len(cached),
            )
        return cached

    symbols = load_universe()
    session = _make_session()
    results = []
    total = len(symbols)
    yahoo_symbols = [f"{s}.KA" for s in symbols]
    today = _last_psx_trading_day()

    # Step 1: Fetch live data from PSX (same-day OHLCV)
    if progress_callback:
        progress_callback(f"Fetching live prices from PSX for {total} stocks...", 0, total)

    psx_live = fetch_psx_live()
    psx_hit = sum(1 for s in symbols if s in psx_live)
    if psx_live and progress_callback:
        progress_callback(f"[PSX] Got live data for {psx_hit}/{total} KMI stocks", 0, total)
    elif not psx_live and progress_callback:
        progress_callback("[PSX] Live fetch failed — will rely on yfinance only", 0, total)

    # Step 2: Fetch historical data from yfinance (for technical indicator lookback)
    if progress_callback:
        progress_callback(f"Batch downloading {total} tickers history from Yahoo Finance...", 0, total)

    try:
        batch = yf.download(
            tickers=yahoo_symbols,
            period=LOOKBACK_DAYS,
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
            session=session,
        )
    except Exception as e:
        error_msg = str(e)
        if progress_callback:
            progress_callback(f"[ERROR] Batch download failed: {error_msg[:120]}", 0, total)
        return []

    if progress_callback:
        progress_callback(f"History downloaded. Computing technicals for {total} stocks...", 0, total)

    # Step 3: Merge live bar + historical, compute technicals
    skipped = []
    for i, symbol in enumerate(symbols):
        yahoo_sym = f"{symbol}.KA"
        try:
            if yahoo_sym not in batch.columns.get_level_values(0):
                skipped.append((symbol, "not in batch result"))
                continue

            df = batch[yahoo_sym].dropna(how="all")
            if df.empty or len(df) < 20:
                skipped.append((symbol, f"insufficient data ({len(df)} rows)"))
                continue

            df = df[["Open", "High", "Low", "Close", "Volume"]]

            # Append today's live bar from PSX if available
            if symbol in psx_live:
                live = psx_live[symbol]
                if live["close"] > 0 and live["volume"] > 0:
                    df = _append_live_bar(df, live, today)

            technicals = compute_technicals(df)
            technicals["symbol"] = symbol
            results.append(technicals)

            if progress_callback and (i + 1) % 10 == 0:
                progress_callback(f"Computed {i + 1}/{total} ({len(results)} OK so far)", i + 1, total)

        except Exception as e:
            skipped.append((symbol, str(e)[:80]))
            continue

    if skipped and progress_callback:
        progress_callback(f"[SKIP] {len(skipped)} symbols had no data: {', '.join(s for s, _ in skipped[:10])}{'...' if len(skipped) > 10 else ''}", len(results), total)

    # Freshness check — warn loudly if the data Yahoo returned is behind the expected trading day.
    if results:
        bar_dates = [r["last_bar_date"] for r in results if r.get("last_bar_date")]
        if bar_dates:
            data_as_of = max(bar_dates)
            expected = _last_psx_trading_day().isoformat()
            if data_as_of < expected and progress_callback:
                progress_callback(
                    f"[STALE] Data is from {data_as_of}, expected {expected}. "
                    f"Yahoo's PSX feed is behind — picks will reflect stale prices.",
                    len(results),
                    total,
                )
            elif progress_callback:
                progress_callback(f"[FRESH] Data as of {data_as_of}", len(results), total)

    # Save to cache only if we got a meaningful chunk of data
    if len(results) >= 20:
        _save_cache(results)
        if progress_callback:
            progress_callback(
                f"[CACHE] Saved {len(results)} stocks to {_cache_path().name}",
                len(results),
                total,
            )

    return results


if __name__ == "__main__":
    # Quick test: fetch first 5 stocks and print results
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
