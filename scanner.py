from data import fetch_all
from agents import run_analysis
from ai_data import fetch_data_via_ai
import json
import re


def parse_trade_plans(raw_output: str) -> list[dict]:
    """
    Parse the strategist agent's raw text output into structured dicts.
    Each dict represents one trade pick.
    """
    picks = []
    # Split on RANK: to isolate each pick block
    blocks = re.split(r"RANK:\s*", raw_output)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        pick = {}
        lines = block.split("\n")

        # First line is the rank number
        try:
            pick["rank"] = int(lines[0].strip())
        except (ValueError, IndexError):
            continue

        for line in lines[1:]:
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().upper()
            value = value.strip()

            if key == "SYMBOL":
                pick["symbol"] = value
            elif key == "CURRENT PRICE":
                pick["price"] = value
            elif key == "BUY RANGE":
                pick["buy_range"] = value
            elif key == "TARGET 1":
                pick["target1"] = value
            elif key == "TARGET 2":
                pick["target2"] = value
            elif key == "STOPLOSS":
                pick["stoploss"] = value
            elif key == "RISK:REWARD" or key == "RISK REWARD":
                pick["rr"] = value
            elif key == "HOLD PERIOD":
                pick["hold"] = value
            elif key == "SIGNALS":
                pick["signals"] = [s.strip() for s in value.split(",")]
            elif key == "REASONING":
                pick["reasoning"] = value

        if "symbol" in pick:
            picks.append(pick)

    return picks


def run_scan(
    trade_style: str = "T+1",
    risk_level: str = "Moderate",
    provider: str = "gemini",
    api_key: str = None,
    use_ai_data: bool = False,
    progress_callback=None,
) -> dict:
    """
    Full scan pipeline:
    1. Fetch OHLCV + compute technicals for all KMI stocks
    2. Pass to CrewAI agents for analysis
    3. Return structured results

    Returns dict with:
        - stocks_scanned: int
        - picks: list of parsed trade plan dicts
        - raw_output: full agent output string
        - error: str or None
    """
    try:
        # Step 1: Data
        if use_ai_data:
            if progress_callback:
                progress_callback("step", f"AI Data Mode — fetching PSX data via {provider.title()}...")
            stocks_data = fetch_data_via_ai(
                api_key=api_key,
                provider=provider,
                progress_callback=progress_callback,
            )
            if not stocks_data:
                return {"error": "AI could not fetch stock data. Try again or switch to yfinance mode.", "picks": [], "stocks_scanned": 0}
        else:
            if progress_callback:
                progress_callback("step", "Fetching OHLCV data for KMI stocks...")

            def fetch_progress(sym, cur, tot):
                if progress_callback:
                    if sym.startswith("[SKIP]"):
                        progress_callback("skip", sym)
                    else:
                        progress_callback("fetch", f"[{cur}/{tot}] Fetching {sym}...")

            stocks_data = fetch_all(progress_callback=fetch_progress)

            if not stocks_data:
                return {"error": "No stock data could be fetched. Yahoo Finance may be rate limiting. Wait a few minutes and try again.", "picks": [], "stocks_scanned": 0}

        # No pre-filtering — agents see all 100 stocks per design decision (BUILD_PLAN.md)
        if progress_callback:
            progress_callback("step", f"Data ready for {len(stocks_data)} stocks. Sending all to AI agents (no pre-filter)...")

        # Step 2: AI Analysis
        raw_output = run_analysis(
            stocks_data=stocks_data,
            trade_style=trade_style,
            risk_level=risk_level,
            provider=provider,
            api_key=api_key,
            progress_callback=progress_callback,
        )

        if progress_callback:
            progress_callback("step", "Parsing trade plans...")

        # Step 3: Parse
        picks = parse_trade_plans(raw_output)

        return {
            "stocks_scanned": len(stocks_data),
            "picks": picks,
            "raw_output": raw_output,
            "error": None,
        }

    except Exception as e:
        return {
            "error": str(e),
            "picks": [],
            "stocks_scanned": 0,
            "raw_output": "",
        }


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    print("Running PSX Scanner...")
    result = run_scan(
        trade_style="T+1",
        risk_level="Moderate",
        provider="gemini",
        progress_callback=lambda type, msg: print(f"  {msg}"),
    )

    if result["error"]:
        print(f"\nError: {result['error']}")
    else:
        print(f"\nStocks scanned: {result['stocks_scanned']}")
        print(f"Picks found: {len(result['picks'])}")
        print("\n--- RAW OUTPUT ---")
        print(result["raw_output"])
