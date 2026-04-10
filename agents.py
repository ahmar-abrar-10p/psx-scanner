from crewai import Agent, Task, Crew, Process, LLM
from langchain_google_genai import ChatGoogleGenerativeAI
from pathlib import Path
from datetime import datetime
import os

PROMPT_LOG_DIR = Path(__file__).parent / "prompt_logs"


def _save_prompt_log(prompts: dict, meta: dict, prefix: str = "scan", title: str = "PSX SCANNER") -> Path:
    """Save rendered agent prompts to a timestamped file for inspection."""
    PROMPT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    suffix = f"_{meta.get('symbol', '')}" if meta.get("symbol") else ""
    path = PROMPT_LOG_DIR / f"{prefix}{suffix}_{ts}.txt"

    lines = []
    lines.append("=" * 80)
    lines.append(f"{title} — PROMPT LOG  ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    lines.append("=" * 80)
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("")

    for agent_name, prompt_text in prompts.items():
        lines.append("=" * 80)
        lines.append(f"AGENT: {agent_name}")
        lines.append("=" * 80)
        lines.append(prompt_text)
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def get_llm(provider: str = "gemini", api_key: str = None):
    """
    Return LangChain LLM instance — used for direct AI calls (data fetching).
    """
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=api_key or os.getenv("GEMINI_API_KEY"),
            temperature=0.3,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=api_key or os.getenv("GROQ_API_KEY"),
            temperature=0.3,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            temperature=0.3,
        )
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(
            model=ollama_model,
            base_url=ollama_base,
            temperature=0.3,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def get_crewai_llm(provider: str = "gemini", api_key: str = None):
    """
    Return CrewAI LLM instance — used for CrewAI agents.
    CrewAI uses its own LLM wrapper, not LangChain objects directly.
    """
    if provider == "gemini":
        gemini_key = api_key or os.getenv("GEMINI_API_KEY")
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
        return LLM(
            model="gemini/gemini-2.0-flash",
            api_key=gemini_key,
            temperature=0.3,
        )
    elif provider == "groq":
        groq_key = api_key or os.getenv("GROQ_API_KEY")
        # litellm requires GROQ_API_KEY env var — setting api_key param alone isn't enough
        if groq_key:
            os.environ["GROQ_API_KEY"] = groq_key
        return LLM(
            model="groq/llama-3.3-70b-versatile",
            api_key=groq_key,
            temperature=0.3,
        )
    elif provider == "openai":
        openai_key = api_key or os.getenv("OPENAI_API_KEY")
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
        return LLM(
            model="openai/gpt-4o-mini",
            api_key=openai_key,
            temperature=0.3,
        )
    elif provider == "ollama":
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return LLM(
            model=f"ollama/{ollama_model}",
            base_url=ollama_base,
            temperature=0.3,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def run_analysis(
    stocks_data: list[dict],
    trade_style: str = "T+1",
    risk_level: str = "Moderate",
    provider: str = "gemini",
    api_key: str = None,
    progress_callback=None,
) -> str:
    """
    Run CrewAI two-agent pipeline on pre-computed stock technicals.

    Agent 1 (Analyst): Screens stocks, identifies technically strong candidates.
    Agent 2 (Strategist): Picks top 10, generates trade plans with entry/target/stoploss/R:R.

    Returns raw string output from Strategist agent.
    """
    llm = get_crewai_llm(provider, api_key)

    # Format stocks data as a readable string for the agents
    stocks_text = _format_stocks_for_agents(stocks_data)

    # --- Agent 1: Technical Analyst ---
    analyst = Agent(
        role="PSX Technical Analyst",
        goal="Screen PSX stocks and identify the strongest technical setups for short-term trades",
        backstory=(
            "You are a senior quantitative analyst with 20 years of experience on the Pakistan Stock Exchange. "
            "You specialize in technical analysis — RSI, EMA crossovers, MACD signals, and volume confirmation. "
            "You are disciplined and data-driven. You only work with the numbers given to you — you never guess or make up data."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    # --- Agent 2: Trade Strategist ---
    strategist = Agent(
        role="PSX Trade Strategist",
        goal="Generate precise, actionable trade plans for the top 10 PSX stocks",
        backstory=(
            "You are a professional PSX trader with 20 years of experience in T+1 and swing trading. "
            "You take the analyst's shortlist and build complete trade plans with exact price levels. "
            "You always calculate entry, target 1, target 2, stoploss, and risk:reward ratio. "
            "You never invent prices — all levels are derived from the technical data provided."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    # --- Task 1: Screen and shortlist ---
    screening_prompt = f"""
You have been given technical data for ALL {len(stocks_data)} PSX Shariah-compliant stocks in the KMI universe.
You MUST analyze every single stock — do NOT skip or filter any out.

STOCK DATA:
{stocks_text}

TRADE STYLE: {trade_style}
RISK LEVEL: {risk_level}

Your job:
1. Analyze ALL {len(stocks_data)} stocks using these technical rules:
   - RSI between 40-70 (momentum without being overbought)
   - Price above EMA20 (uptrend confirmation)
   - Volume ratio > 1.2 (above average volume — institutional interest)
   - MACD histogram positive or turning positive (bullish momentum)
2. For EVERY stock, compute a confluence score (0-4) based on how many of the above criteria are met.
3. Output the TOP 100 stocks ranked by confluence score descending, then by volume ratio descending as tiebreaker.
   Include symbol, price, RSI, EMA status, volume ratio, MACD status, and confluence score for each.

IMPORTANT: You must analyze ALL {len(stocks_data)} stocks before ranking. Do not skip any during analysis.
Output the top 100 after ranking — the next agent needs a broad pool to pick from.
"""
    screening_task = Task(
        description=screening_prompt,
        expected_output="Top 100 stocks ranked by confluence score (0-4), with symbol, price, RSI, EMA status, volume ratio, MACD status, and confluence score",
        agent=analyst,
    )

    # --- Task 2: Generate trade plans ---
    strategist_prompt = f"""
Using the analyst's ranked top 100 candidates, select the TOP 10 highest-conviction setups and generate complete trade plans.

TRADE STYLE: {trade_style}
RISK LEVEL: {risk_level}

For each of the top 10 stocks, provide EXACTLY this format:

RANK: [1-10]
SYMBOL: [ticker]
CURRENT PRICE: [price in PKR]
BUY RANGE: [entry low] - [entry high]  (within 0.5% of current price)
TARGET 1: [price] ([% gain])
TARGET 2: [price] ([% gain])
STOPLOSS: [price] ([% loss]) — use ATR-based stoploss (price - 1.5 x ATR14)
RISK:REWARD: [ratio]
HOLD PERIOD: {trade_style}
SIGNALS: [list of triggered signals]
REASONING: [2-3 sentences max explaining the setup]

Rules for price levels:
- T+1: Target 1 = 2-3% above entry, Target 2 = 4-5% above entry
- Swing 3-5d: Target 1 = 4-6% above entry, Target 2 = 8-12% above entry
- Conservative risk: stoploss at 1x ATR14 below entry
- Moderate risk: stoploss at 1.5x ATR14 below entry
- Aggressive risk: stoploss at 2x ATR14 below entry
- Minimum R:R ratio must be 1.5:1

Rank by overall conviction (confluence of signals + momentum strength).
"""
    trade_plan_task = Task(
        description=strategist_prompt,
        expected_output="Top 10 complete trade plans in the exact format specified above",
        agent=strategist,
        context=[screening_task],
    )

    # --- Save prompts for inspection ---
    log_path = _save_prompt_log(
        prompts={
            "1. Technical Analyst (screening_task)": screening_prompt,
            "2. Trade Strategist (trade_plan_task)": strategist_prompt,
        },
        meta={
            "stocks_count": len(stocks_data),
            "trade_style": trade_style,
            "risk_level": risk_level,
            "provider": provider,
        },
    )
    if progress_callback:
        progress_callback("step", f"📝 Prompts saved to {log_path.name} ({log_path.parent.name}/)")
        # Surface a short preview into the UI log so user can see the rendered table without opening the file
        preview_lines = stocks_text.split("\n")[:5]
        preview = "\n".join(preview_lines) + f"\n... ({len(stocks_data)} stocks total)"
        progress_callback("step", f"📋 Prompt preview (first 5 stocks of the data table sent to Analyst):\n{preview}")

    # --- Run the crew ---
    crew = Crew(
        agents=[analyst, strategist],
        tasks=[screening_task, trade_plan_task],
        process=Process.sequential,
        verbose=False,
    )

    import time
    for attempt in range(3):
        try:
            result = crew.kickoff()
            return str(result)
        except Exception as e:
            error_msg = str(e)
            if ("rate_limit" in error_msg.lower() or "429" in error_msg or "RateLimitError" in error_msg) and attempt < 2:
                wait = 15 * (attempt + 1)
                print(f"[CrewAI] Rate limit hit, waiting {wait}s before retry {attempt+2}/3...")
                time.sleep(wait)
            else:
                raise


    return path


def run_deep_analysis_ai(
    symbol: str,
    company_name: str,
    sector: str = "Unknown",
    computation_log: str = "",
    confluence_text: str = "",
    provider: str = "gemini",
    api_key: str = None,
    progress_callback=None,
) -> str:
    """
    Run two-agent pipeline for single-stock deep analysis:
    Agent 1 (News Scout): Searches for recent news/events for the stock.
    Agent 2 (Senior Analyst): Synthesizes all technicals + news into a verdict.

    Returns raw string output from the Senior Analyst.
    """
    llm = get_crewai_llm(provider, api_key)

    # --- Agent 1: News & Events Scout ---
    news_scout = Agent(
        role="PSX News & Events Scout",
        goal=f"Find recent news, corporate actions, sector developments, and market events relevant to {symbol} ({company_name}) in the {sector} sector",
        backstory=(
            "You are a financial news analyst specialized in the Pakistan Stock Exchange. "
            "You track corporate announcements, earnings, dividends, right issues, board meetings, "
            "regulatory actions, and sector-wide developments. You are thorough but concise. "
            "You only report facts you are confident about — never speculate or fabricate news."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    news_prompt = f"""
Research recent news and events for {symbol} ({company_name}) on the Pakistan Stock Exchange.
This company belongs to the **{sector}** sector.

Report on these categories (if applicable):

COMPANY-SPECIFIC:
1. EARNINGS: Recent quarterly/annual results, EPS, profit growth
2. DIVIDENDS: Recent or upcoming dividend declarations, ex-dates
3. CORPORATE ACTIONS: Right issues, bonus shares, stock splits, mergers
4. BOARD/AGM: Upcoming board meetings or AGMs
5. REGULATORY: SECP notices, compliance issues

SECTOR-WIDE ({sector}):
6. SECTOR POLICY: Government policies, regulations, taxes, duties affecting the {sector} sector
7. SECTOR DEMAND: Demand trends, pricing changes, input cost changes for {sector}
8. SECTOR PEERS: How are peer companies in {sector} performing? Any sector rotation happening?
9. MACRO FACTORS: SBP interest rate decisions, PKR exchange rate, inflation — specifically how they impact {sector}

MARKET:
10. MARKET SENTIMENT: Any significant analyst coverage, institutional interest, or index rebalancing

Output format:
NEWS_SENTIMENT: POSITIVE / NEGATIVE / NEUTRAL / UNKNOWN
KEY_EVENTS:
- [event 1]
- [event 2]
RISK_FLAGS:
- [risk 1] (or "None identified")
CATALYST:
- [upcoming catalyst that could move the price] (or "None identified")

IMPORTANT: If you are not confident about specific news for this stock, say "No confirmed recent news found"
rather than fabricating information. Being honest about uncertainty is more valuable than guessing.
"""

    news_task = Task(
        description=news_prompt,
        expected_output="News sentiment, key events, risk flags, and catalysts for the stock",
        agent=news_scout,
    )

    # --- Agent 2: Senior Stock Analyst ---
    analyst = Agent(
        role="Senior PSX Stock Analyst",
        goal=f"Provide a definitive BUY, AVOID, or WAIT verdict for {symbol}",
        backstory=(
            "You are a senior stock analyst with 25 years on the Pakistan Stock Exchange. "
            "You specialize in multi-timeframe technical analysis combining trend, momentum, "
            "volume, volatility, and price level techniques. You also consider news and events. "
            "You are disciplined and data-driven — you never guess or fabricate data. "
            "You weigh all evidence, identify conflicts, and produce clear, actionable verdicts."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    analyst_prompt = f"""
You are analyzing {symbol} ({company_name}) on the Pakistan Stock Exchange.

Below are the results of 17 technical analysis techniques computed on 90 days of OHLCV data,
plus a news report from our News Scout agent.

=== COMPUTATION LOG ===
{computation_log}

=== CONFLUENCE SUMMARY ===
{confluence_text}

=== INSTRUCTIONS ===
Synthesize ALL the evidence above — technicals AND news — and provide your verdict.

Consider:
- Do the signals agree or conflict?
- Which timeframe does the setup favor? (T+1, Swing 3-5d, Positional 2-4w)
- Are there any news-based risks that override the technical picture?
- Is the risk:reward favorable (minimum 1.5:1)?

TARGET RANGE RULES (choose targets that match the timeframe):
- T+1: Target 1 = 2-3% above entry, Target 2 = 4-5% above entry
- Swing 3-5d: Target 1 = 4-6% above entry, Target 2 = 8-12% above entry
- Positional 2-4w: Target 1 = 8-12% above entry, Target 2 = 15-20% above entry
- Pick the nearest REAL level from the computed technicals that falls in the target range.
  For example, if Fib 38.2% is at +5% and you're doing Swing, that's a good Target 1.
  If P&F target is at +13%, that's a good Target 2.
- If no computed level falls in the range, use ATR multiples (e.g., entry + 2×ATR for T1).

STOPLOSS RULES:
- Conservative: 1×ATR below entry
- Moderate: 1.5×ATR below entry
- Aggressive: 2×ATR below entry
- Prefer a stoploss that aligns with a support level (Pivot S1, Fib level, Value Area Low).

OTHER RULES:
- Entry must be within 1% of the current price.
- R:R must be >= 1.5:1 for a BUY verdict (calculated using Target 1, not Target 2).
- Heavy conflict between signals → WAIT (not enough clarity).
- AVOID = bearish evidence dominates (not just uncertainty — that's WAIT).
- If news reveals a major risk (e.g., regulatory action, earnings miss), factor it prominently.

Output EXACTLY this format:

VERDICT: [BUY / AVOID / WAIT]
CONVICTION: [1-10]
TIMEFRAME: [T+1 / Swing 3-5d / Positional 2-4w]
ENTRY: [price or range]
STOPLOSS: [price] ([which technique/level])
TARGET 1: [price] ([% gain]) ([which technique/level])
TARGET 2: [price] ([% gain]) ([which technique/level])
RISK_REWARD: [ratio]
BULLISH_SIGNALS: [comma-separated list of bullish techniques]
BEARISH_SIGNALS: [comma-separated list of bearish techniques]
CONFLICTS: [describe any contradictions between signals, or "None"]
NEWS_IMPACT: [how news affects the verdict, or "No significant news impact"]
REASONING: [3-5 sentence synthesis explaining your verdict]
"""

    analyst_task = Task(
        description=analyst_prompt,
        expected_output="Complete verdict with BUY/AVOID/WAIT, conviction, entry, stoploss, targets, and reasoning",
        agent=analyst,
        context=[news_task],
    )

    # Run crew
    crew = Crew(
        agents=[news_scout, analyst],
        tasks=[news_task, analyst_task],
        process=Process.sequential,
        verbose=False,
    )

    import time
    for attempt in range(3):
        try:
            if progress_callback:
                progress_callback("step", f"Running AI analysis (attempt {attempt + 1}/3)...")
            result = crew.kickoff()
            return str(result)
        except Exception as e:
            error_msg = str(e)
            if ("rate_limit" in error_msg.lower() or "429" in error_msg or "RateLimitError" in error_msg) and attempt < 2:
                wait = 15 * (attempt + 1)
                if progress_callback:
                    progress_callback("step", f"Rate limit hit, waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise


def _format_stocks_for_agents(stocks_data: list[dict]) -> str:
    """Format stock technicals as a clean text table for agent context."""
    lines = []
    lines.append(f"{'SYMBOL':<10} {'PRICE':>8} {'RSI14':>6} {'EMA20':>8} {'EMA50':>8} {'MACD_H':>8} {'VOL_RATIO':>10} {'ATR14':>7} {'52W_H':>8} {'52W_L':>8}")
    lines.append("-" * 95)
    for s in stocks_data:
        lines.append(
            f"{s.get('symbol',''):<10} "
            f"{s.get('price', 0):>8.2f} "
            f"{s.get('rsi14', 0) or 0:>6.1f} "
            f"{s.get('ema20', 0) or 0:>8.2f} "
            f"{s.get('ema50', 0) or 0:>8.2f} "
            f"{s.get('macd_hist', 0) or 0:>8.4f} "
            f"{s.get('volume_ratio', 0) or 0:>10.2f} "
            f"{s.get('atr14', 0) or 0:>7.2f} "
            f"{s.get('week52_high', 0) or 0:>8.2f} "
            f"{s.get('week52_low', 0) or 0:>8.2f}"
        )
    return "\n".join(lines)
