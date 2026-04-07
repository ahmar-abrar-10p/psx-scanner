from crewai import Agent, Task, Crew, Process
from langchain_google_genai import ChatGoogleGenerativeAI
import os


def get_llm(provider: str = "gemini", api_key: str = None):
    """
    Return LLM instance based on provider selection.
    Easily extensible to add more providers.
    """
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=api_key or os.getenv("GEMINI_API_KEY"),
            temperature=0.3,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
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
) -> str:
    """
    Run CrewAI two-agent pipeline on pre-computed stock technicals.

    Agent 1 (Analyst): Screens stocks, identifies technically strong candidates.
    Agent 2 (Strategist): Picks top 10, generates trade plans with entry/target/stoploss/R:R.

    Returns raw string output from Strategist agent.
    """
    llm = get_llm(provider, api_key)

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
    screening_task = Task(
        description=f"""
You have been given technical data for {len(stocks_data)} PSX Shariah-compliant stocks.

STOCK DATA:
{stocks_text}

TRADE STYLE: {trade_style}
RISK LEVEL: {risk_level}

Your job:
1. Screen all stocks using these technical rules:
   - RSI between 40-70 (momentum without being overbought)
   - Price above EMA20 (uptrend confirmation)
   - Volume ratio > 1.2 (above average volume — institutional interest)
   - MACD histogram positive or turning positive (bullish momentum)
2. Rank candidates by confluence (how many signals align)
3. Output a shortlist of 15-20 best candidates with their key metrics

Be strict. Only include stocks that meet at least 3 of the 4 criteria.
""",
        expected_output="A shortlist of 15-20 stocks with symbol, price, RSI, EMA status, volume ratio, MACD status, and confluence score",
        agent=analyst,
    )

    # --- Task 2: Generate trade plans ---
    trade_plan_task = Task(
        description=f"""
Using the analyst's shortlist, generate complete trade plans for the TOP 10 stocks.

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
""",
        expected_output="Top 10 complete trade plans in the exact format specified above",
        agent=strategist,
        context=[screening_task],
    )

    # --- Run the crew ---
    crew = Crew(
        agents=[analyst, strategist],
        tasks=[screening_task, trade_plan_task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff()
    return str(result)


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
