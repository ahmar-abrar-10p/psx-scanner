"""
ohlcv_store.py — Persistent local OHLCV history for all KMI stocks.

Stores per-stock parquet files in cache/ohlcv/.  Initial backfill fetches 6 months
from yfinance; daily runs append only the missing days.  History is capped at 1 year.
"""
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

OHLCV_DIR = Path(__file__).parent / "cache" / "ohlcv"
BACKFILL_PERIOD = "6mo"
MAX_HISTORY_DAYS = 365
FETCH_DELAY = 1.0  # seconds between individual yfinance calls

# PSX symbol → Yahoo Finance symbol mapping.
# Some PSX tickers have different symbols on Yahoo or are missing entirely.
YAHOO_TICKER_MAP = {
    "ENGROH": "DAWH",
}


def _yahoo_symbol(psx_symbol: str) -> str:
    """Convert a PSX symbol to its Yahoo Finance ticker (with .KA suffix)."""
    mapped = YAHOO_TICKER_MAP.get(psx_symbol, psx_symbol)
    return f"{mapped}.KA"


def _last_psx_trading_day(today: date | None = None) -> date:
    """Most recent PSX trading day (Mon-Fri) on or before `today`.
    PSX is closed Sat/Sun. Does not account for public holidays."""
    d = today or date.today()
    while d.weekday() >= 5:
        d = date.fromordinal(d.toordinal() - 1)
    return d


def _make_session():
    """curl_cffi session with chrome impersonation — required for Yahoo crumb flow."""
    return curl_requests.Session(verify=False, impersonate="chrome")


def _ohlcv_path(symbol: str) -> Path:
    return OHLCV_DIR / f"{symbol}.parquet"


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure consistent format: tz-naive DatetimeIndex, standard OHLCV columns, sorted, deduped."""
    if df.empty:
        return df
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    return df


def _truncate(df: pd.DataFrame) -> pd.DataFrame:
    """Keep at most MAX_HISTORY_DAYS of data, trimming the oldest rows."""
    if df.empty:
        return df
    cutoff = df.index[-1] - pd.Timedelta(days=MAX_HISTORY_DAYS)
    return df[df.index >= cutoff]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_ohlcv(symbol: str) -> pd.DataFrame | None:
    """Load stored OHLCV for a symbol. Returns None if no file exists."""
    p = _ohlcv_path(symbol)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logger.warning("Failed to load %s: %s", p.name, e)
        return None


def save_ohlcv(symbol: str, df: pd.DataFrame) -> None:
    """Save OHLCV DataFrame to parquet. Normalizes, deduplicates, and truncates."""
    OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    df = _normalize_df(df)
    df = _truncate(df)
    df.to_parquet(_ohlcv_path(symbol))


def last_stored_date(symbol: str) -> date | None:
    """Return the last date in the stored OHLCV, or None."""
    df = load_ohlcv(symbol)
    if df is None or df.empty:
        return None
    return df.index[-1].date()


def update_single(symbol: str, session=None) -> pd.DataFrame | None:
    """
    Incremental update for one stock.
    - No existing data → full backfill (6mo).
    - Existing data up to date → return as-is.
    - Existing data stale → fetch only the delta and merge.
    Returns the full updated DataFrame, or None if yfinance has nothing.
    """
    if session is None:
        session = _make_session()

    reference = _last_psx_trading_day()
    existing = load_ohlcv(symbol)
    yahoo_sym = _yahoo_symbol(symbol)

    if existing is None or existing.empty:
        # Full backfill
        ticker = yf.Ticker(yahoo_sym, session=session)
        df = ticker.history(period=BACKFILL_PERIOD, interval="1d")
        if df is None or df.empty:
            return None
        df = _normalize_df(df)
        save_ohlcv(symbol, df)
        return df

    last = existing.index[-1].date()
    if last >= reference:
        return existing  # already up to date

    # Incremental fetch
    start = last + timedelta(days=1)
    ticker = yf.Ticker(yahoo_sym, session=session)
    new_data = ticker.history(start=start.isoformat(),
                              end=(reference + timedelta(days=1)).isoformat(),
                              interval="1d")

    if new_data is not None and not new_data.empty:
        new_data = _normalize_df(new_data)
        df = pd.concat([existing, new_data])
        df = _normalize_df(df)
    else:
        df = existing  # no new data (holidays, weekend, yfinance lag)

    save_ohlcv(symbol, df)
    return df


def update_batch(
    symbols: list[str],
    session=None,
    progress_callback=None,
) -> dict[str, pd.DataFrame]:
    """
    Update OHLCV for multiple symbols efficiently.
    Groups into: needs_backfill, needs_incremental, up_to_date.
    Uses batch yf.download() for both groups to minimize network calls.
    """
    if session is None:
        session = _make_session()

    reference = _last_psx_trading_day()
    needs_backfill = []
    needs_incremental = []  # (symbol, existing_df)
    up_to_date = {}

    for sym in symbols:
        existing = load_ohlcv(sym)
        if existing is None or existing.empty:
            needs_backfill.append(sym)
        elif existing.index[-1].date() >= reference:
            up_to_date[sym] = existing
        else:
            needs_incremental.append((sym, existing))

    total = len(symbols)
    if progress_callback:
        progress_callback(
            f"OHLCV store: {len(up_to_date)} up-to-date, "
            f"{len(needs_incremental)} need update, "
            f"{len(needs_backfill)} need backfill",
            0, total,
        )

    results = dict(up_to_date)

    # Batch backfill for stocks with no data
    if needs_backfill:
        if progress_callback:
            progress_callback(
                f"Backfilling {len(needs_backfill)} stocks (6mo history)...",
                len(results), total,
            )
        yahoo_syms = [_yahoo_symbol(s) for s in needs_backfill]
        try:
            batch = yf.download(
                tickers=yahoo_syms,
                period=BACKFILL_PERIOD,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
                session=session,
            )
            for sym in needs_backfill:
                yahoo_sym = _yahoo_symbol(sym)
                try:
                    if len(needs_backfill) == 1:
                        df = batch.dropna(how="all")
                    else:
                        if yahoo_sym not in batch.columns.get_level_values(0):
                            continue
                        df = batch[yahoo_sym].dropna(how="all")
                    if df.empty or len(df) < 5:
                        continue
                    df = _normalize_df(df)
                    save_ohlcv(sym, df)
                    results[sym] = df
                except Exception as e:
                    logger.warning("Backfill failed for %s: %s", sym, e)
        except Exception as e:
            logger.error("Batch backfill download failed: %s", e)

        if progress_callback:
            progress_callback(
                f"Backfill complete: {len(results) - len(up_to_date)} stocks saved",
                len(results), total,
            )

    # Batch incremental update for stale stocks
    if needs_incremental:
        if progress_callback:
            progress_callback(
                f"Updating {len(needs_incremental)} stale stocks...",
                len(results), total,
            )
        oldest_stale = min(ex.index[-1].date() for _, ex in needs_incremental)
        start = oldest_stale + timedelta(days=1)
        yahoo_syms = [_yahoo_symbol(s) for s, _ in needs_incremental]

        try:
            batch = yf.download(
                tickers=yahoo_syms,
                start=start.isoformat(),
                end=(reference + timedelta(days=1)).isoformat(),
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
                session=session,
            )
            for sym, existing in needs_incremental:
                yahoo_sym = _yahoo_symbol(sym)
                try:
                    if len(needs_incremental) == 1:
                        new_data = batch.dropna(how="all")
                    else:
                        if yahoo_sym not in batch.columns.get_level_values(0):
                            # No new data from Yahoo — keep existing
                            results[sym] = existing
                            continue
                        new_data = batch[yahoo_sym].dropna(how="all")

                    if new_data is not None and not new_data.empty:
                        new_data = _normalize_df(new_data)
                        df = pd.concat([existing, new_data])
                        df = _normalize_df(df)
                    else:
                        df = existing

                    save_ohlcv(sym, df)
                    results[sym] = df
                except Exception as e:
                    logger.warning("Incremental update failed for %s: %s", sym, e)
                    results[sym] = existing  # keep what we had
        except Exception as e:
            logger.error("Batch incremental download failed: %s", e)
            # Fall back to existing data
            for sym, existing in needs_incremental:
                results[sym] = existing

        if progress_callback:
            progress_callback(
                f"Update complete: {len(results)} stocks ready",
                len(results), total,
            )

    return results


def backfill_all(
    symbols: list[str],
    session=None,
    progress_callback=None,
) -> dict[str, pd.DataFrame]:
    """
    Delete all stored OHLCV and re-fetch 6 months for all symbols.
    Called by the 'Generate History' UI button.
    """
    clear_store()
    if progress_callback:
        progress_callback(f"Cleared OHLCV store. Downloading 6mo history for {len(symbols)} stocks...", 0, len(symbols))
    return update_batch(symbols, session=session, progress_callback=progress_callback)


def clear_store(symbols: list[str] | None = None) -> int:
    """Delete stored OHLCV files. If symbols is None, delete all. Returns count deleted."""
    if not OHLCV_DIR.exists():
        return 0
    count = 0
    if symbols is None:
        for f in OHLCV_DIR.glob("*.parquet"):
            f.unlink()
            count += 1
    else:
        for sym in symbols:
            p = _ohlcv_path(sym)
            if p.exists():
                p.unlink()
                count += 1
    return count


def store_stats() -> dict:
    """Return stats about the OHLCV store."""
    if not OHLCV_DIR.exists():
        return {"count": 0, "total_size_kb": 0, "oldest": None, "newest": None}

    files = list(OHLCV_DIR.glob("*.parquet"))
    if not files:
        return {"count": 0, "total_size_kb": 0, "oldest": None, "newest": None}

    total_size = sum(f.stat().st_size for f in files)
    oldest_date = None
    newest_date = None

    for f in files:
        try:
            df = pd.read_parquet(f)
            df.index = pd.to_datetime(df.index)
            if not df.empty:
                first = df.index[0].date()
                last = df.index[-1].date()
                if oldest_date is None or first < oldest_date:
                    oldest_date = first
                if newest_date is None or last > newest_date:
                    newest_date = last
        except Exception:
            continue

    return {
        "count": len(files),
        "total_size_kb": round(total_size / 1024, 1),
        "oldest": oldest_date.isoformat() if oldest_date else None,
        "newest": newest_date.isoformat() if newest_date else None,
    }


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Quick test: backfill 3 stocks
    test_symbols = ["OGDC", "MEBL", "LUCK"]
    session = _make_session()

    print("Testing update_single for OGDC...")
    df = update_single("OGDC", session)
    if df is not None:
        print(f"  Got {len(df)} bars, {df.index[0].date()} to {df.index[-1].date()}")
    else:
        print("  No data returned")

    print(f"\nStore stats: {store_stats()}")
