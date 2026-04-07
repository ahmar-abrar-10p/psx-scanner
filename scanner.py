from data import fetch_all
from agents import run_analysis
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
    progress_callback=None,
) -> dict:
    """
    Full scan pipeline:
    1. Fetch OHLCV + compute technicals for all 100 stocks
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
        if progress_callback:
            progress_callback("step", "Fetching OHLCV data for 100 stocks...")

        stocks_data = fetch_all(
            progress_callback=lambda sym, cur, tot: progress_callback("fetch", f"[{cur}/{tot}] Fetching {sym}...") if progress_callback else None
        )

        if not stocks_data:
            return {"error": "No stock data could be fetched. Check your internet connection.", "picks": [], "stocks_scanned": 0}

        if progress_callback:
            progress_callback("step", f"Data fetched for {len(stocks_data)} stocks. Running AI analysis...")

        # Step 2: AI Analysis
        raw_output = run_analysis(
            stocks_data=stocks_data,
            trade_style=trade_style,
            risk_level=risk_level,
            provider=provider,
            api_key=api_key,
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
