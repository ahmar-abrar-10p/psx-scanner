"""
AI-based data fetching — uses the selected AI provider to fetch PSX stock data.
Uses the same LLM as the CrewAI agents — single provider for the whole app.

Note: Gemini with Google Search grounding gives live prices.
      Other providers (Groq, OpenAI) use their training data — less accurate for prices
      but still useful for getting the pipeline working when yfinance is unavailable.
"""

import json
from agents import get_llm
from data import load_universe



DATA_FETCH_PROMPT = """
You are a data collection agent for Pakistan Stock Exchange (PSX).

Look up current stock data for these PSX tickers:
{symbols}

STRICT RULES:
1. Only include a stock if you are confident about its price
2. If unsure about a price — skip that stock, do NOT guess
3. Prices must be in PKR (Pakistani Rupees)
4. Return ONLY a JSON array, no explanation, no markdown

Each object must have:
- symbol: ticker string
- price: last closing price in PKR (number)
- high: day high (number, use price if unknown)
- low: day low (number, use price if unknown)
- volume: trading volume (number, use 0 if unknown)
- change_pct: % change today (number, use 0 if unknown)

Return raw JSON only, starting with [ and ending with ]
"""

TECHNICALS_PROMPT = """
You are a quantitative analyst for Pakistan Stock Exchange (PSX).

You have been given current stock price data:
{stock_data}

For each stock, compute or estimate realistic technical indicators and return a JSON array.

Each object must have:
- symbol: ticker
- price: current price (use exact price given)
- rsi14: RSI(14) value between 0-100
- ema20: EMA(20) value (typically within 3-5% of current price)
- ema50: EMA(50) value (typically within 5-10% of current price)
- macd_hist: MACD histogram (positive=bullish, negative=bearish, typically -5 to +5)
- volume_ratio: today volume / 20-day avg volume (1.0 = average, >1.5 = high volume)
- atr14: ATR(14) value (typically 1.5-3% of price for PSX stocks)
- week52_high: 52-week high price
- week52_low: 52-week low price
- price_vs_ema20: % difference (price - ema20) / ema20 * 100
- price_vs_ema50: % difference (price - ema50) / ema50 * 100

Return ONLY the JSON array, no explanation, no markdown.
"""


def extract_json(text: str) -> list:
    """Extract JSON array from AI response text, handling markdown code blocks."""
    # Strip markdown code blocks if present
    if "```" in text:
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return []
    return []


def fetch_data_via_ai(
    api_key: str,
    provider: str = "gemini",
    progress_callback=None,
) -> list[dict]:
    """
    Fetch PSX stock data using the selected AI provider.
    Uses exactly 2 API calls:
      Call 1: fetch prices for all stocks
      Call 2: compute technicals from those prices
    """
    all_symbols = load_universe()
    # Limit to top 50 for AI mode — 100 stocks makes the response too long to parse reliably
    symbols = all_symbols[:50]
    llm = get_llm(provider=provider, api_key=api_key)

    def invoke(prompt: str) -> str:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    # Call 1: fetch prices
    if progress_callback:
        progress_callback("fetch", f"[AI:{provider}] Fetching PSX prices for {len(symbols)} stocks...")

    try:
        text = invoke(DATA_FETCH_PROMPT.format(symbols=", ".join(symbols)))
        all_price_data = extract_json(text)
        if not all_price_data:
            if progress_callback:
                progress_callback("skip", f"[AI:{provider}] No valid price data returned. Check console for raw response.")
            return []
        if progress_callback:
            progress_callback("fetch", f"[AI:{provider}] Got price data for {len(all_price_data)} stocks")
    except Exception as e:
        error_msg = str(e)
        print(f"[AI:{provider}] Price fetch error: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "rate_limit" in error_msg.lower():
            if progress_callback:
                progress_callback("skip", f"[AI:{provider}] Rate limit hit. Wait a few minutes and try again.")
        else:
            if progress_callback:
                progress_callback("skip", f"[AI:{provider}] Price fetch failed: {error_msg}")
        return []

    # Call 2: compute technicals
    if progress_callback:
        progress_callback("step", f"[AI:{provider}] Computing technicals for {len(all_price_data)} stocks...")

    stock_text = "\n".join([
        f"{s.get('symbol')}: price={s.get('price')}, high={s.get('high')}, low={s.get('low')}, volume={s.get('volume')}, change%={s.get('change_pct')}"
        for s in all_price_data
    ])

    try:
        text = invoke(TECHNICALS_PROMPT.format(stock_data=stock_text))
        technicals = extract_json(text)
        if technicals:
            if progress_callback:
                progress_callback("step", f"[AI:{provider}] Technicals ready for {len(technicals)} stocks")
            return technicals
        else:
            if progress_callback:
                progress_callback("skip", f"[AI:{provider}] Technicals parse failed — using estimates")
            return _estimate_technicals(all_price_data)
    except Exception as e:
        error_msg = str(e)
        print(f"[AI:{provider}] Technicals error: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "rate_limit" in error_msg.lower():
            if progress_callback:
                progress_callback("skip", f"[AI:{provider}] Rate limit hit on technicals call. Using estimates.")
        else:
            if progress_callback:
                progress_callback("skip", f"[AI:{provider}] Technicals failed: {error_msg}")
        return _estimate_technicals(all_price_data)


def _estimate_technicals(price_data: list[dict]) -> list[dict]:
    """Fallback: derive basic technicals from price data."""
    results = []
    for s in price_data:
        price = s.get("price", 0)
        if not price:
            continue
        results.append({
            "symbol": s.get("symbol"),
            "price": price,
            "rsi14": 55.0,
            "ema20": round(price * 0.97, 2),
            "ema50": round(price * 0.94, 2),
            "macd_hist": 0.5,
            "volume_ratio": 1.2,
            "atr14": round(price * 0.02, 2),
            "week52_high": s.get("high", round(price * 1.3, 2)),
            "week52_low": s.get("low", round(price * 0.7, 2)),
            "price_vs_ema20": 3.0,
            "price_vs_ema50": 6.0,
        })
    return results
