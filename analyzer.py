"""
Single-stock deep analysis orchestration pipeline.
Fetches data → runs 17 techniques → sends to AI → returns structured verdict.
Writes a comprehensive log of every step.
"""

import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from data import fetch_single_stock, compute_technicals
from deep_analysis import run_deep_analysis
from agents import run_deep_analysis_ai

UNIVERSE_FILE = Path(__file__).parent / "KMI_top100.csv"
LOG_DIR = Path(__file__).parent / "prompt_logs"


def _get_company_info(symbol: str) -> tuple[str, str]:
    """Look up company name and sector from KMI_top100.csv. Returns (name, sector)."""
    try:
        df = pd.read_csv(UNIVERSE_FILE)
        match = df[df["symbol"] == symbol]
        if not match.empty:
            name = match.iloc[0]["name"]
            sector = match.iloc[0].get("sector", "Unknown")
            return name, sector
    except Exception:
        pass
    return symbol, "Unknown"


class AnalysisLog:
    """Accumulates log sections and writes them to a file at the end."""

    def __init__(self, symbol: str, provider: str):
        self.symbol = symbol
        self.provider = provider
        self.lines = []
        self.ts = datetime.now()
        self._header()

    def _header(self):
        self.lines.append("=" * 90)
        self.lines.append(f"PSX STOCK ANALYZER — FULL ANALYSIS LOG")
        self.lines.append(f"Generated: {self.ts.strftime('%Y-%m-%d %H:%M:%S')}")
        self.lines.append(f"Symbol: {self.symbol}  |  Provider: {self.provider}")
        self.lines.append("=" * 90)
        self.lines.append("")

    def section(self, title: str):
        self.lines.append("")
        self.lines.append("=" * 90)
        self.lines.append(f"  {title}")
        self.lines.append("=" * 90)
        self.lines.append("")

    def subsection(self, title: str):
        self.lines.append("")
        self.lines.append(f"--- {title} ---")
        self.lines.append("")

    def text(self, content: str):
        self.lines.append(content)

    def kv(self, key: str, value):
        self.lines.append(f"  {key}: {value}")

    def table_row(self, *cols):
        self.lines.append("  ".join(str(c) for c in cols))

    def blank(self):
        self.lines.append("")

    def save(self) -> Path:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts_str = self.ts.strftime("%Y-%m-%d_%H-%M-%S")
        path = LOG_DIR / f"analysis_{self.symbol}_{ts_str}.txt"
        path.write_text("\n".join(self.lines), encoding="utf-8")
        return path


def format_log_for_display(log_entries: list[dict]) -> list[dict]:
    """Convert log entries to flat dicts for Streamlit table display."""
    rows = []
    for entry in log_entries:
        vals = entry.get("values", {})
        val_parts = []
        for k, v in vals.items():
            if isinstance(v, dict):
                val_parts.append(f"{k}: {{{', '.join(f'{kk}={vv}' for kk, vv in v.items())}}}")
            elif isinstance(v, list):
                val_parts.append(f"{k}: {', '.join(str(x) for x in v)}")
            else:
                val_parts.append(f"{k}={v}")
        rows.append({
            "Technique": entry["name"],
            "Signal": entry["signal"],
            "Details": "; ".join(val_parts) if val_parts else "—",
            "Reason": entry["reason"],
        })
    return rows


def format_log_for_ai(log_entries: list[dict]) -> str:
    """Format log entries as text for the AI agent prompt."""
    lines = []
    for entry in log_entries:
        vals = entry.get("values", {})
        val_str = ", ".join(
            f"{k}={v}" for k, v in vals.items()
            if not isinstance(v, (dict, list))
        )
        lines.append(f"[{entry['signal']}] {entry['name']}: {val_str} -- {entry['reason']}")
    return "\n".join(lines)


def parse_verdict(raw_output: str) -> dict:
    """Parse structured AI verdict output into a dict."""
    verdict = {}
    lines = raw_output.split("\n")

    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        value = value.strip()

        if key == "VERDICT":
            verdict["verdict"] = value
        elif key == "CONVICTION":
            try:
                verdict["conviction"] = int(re.search(r"\d+", value).group())
            except (AttributeError, ValueError):
                verdict["conviction"] = value
        elif key == "TIMEFRAME":
            verdict["timeframe"] = value
        elif key == "ENTRY":
            verdict["entry"] = value
        elif key == "STOPLOSS":
            verdict["stoploss"] = value
        elif key == "TARGET 1":
            verdict["target1"] = value
        elif key == "TARGET 2":
            verdict["target2"] = value
        elif key == "RISK_REWARD":
            verdict["risk_reward"] = value
        elif key == "BULLISH_SIGNALS":
            verdict["bullish_signals"] = [s.strip() for s in value.split(",")]
        elif key == "BEARISH_SIGNALS":
            verdict["bearish_signals"] = [s.strip() for s in value.split(",")]
        elif key == "CONFLICTS":
            verdict["conflicts"] = value
        elif key == "NEWS_IMPACT":
            verdict["news_impact"] = value
        elif key == "REASONING":
            verdict["reasoning"] = value

    return verdict


def run_single_stock_analysis(
    symbol: str,
    provider: str = "gemini",
    api_key: str = None,
    progress_callback=None,
) -> dict:
    """
    Full single-stock analysis pipeline:
    1. Fetch 90-day OHLCV + PSX live bar
    2. Compute 17 technical techniques + confluence
    3. Send to AI (News Scout + Senior Analyst)
    4. Parse and return structured result

    Returns dict with: symbol, price, change, volume, basic_technicals,
    computation_log, confluence, verdict, raw_output, error
    """
    log = AnalysisLog(symbol, provider)

    try:
        # =====================================================================
        # STEP 1: FETCH DATA
        # =====================================================================
        if progress_callback:
            progress_callback("step", f"Fetching data for {symbol}...")

        df, live_bar = fetch_single_stock(symbol, progress_callback=progress_callback)

        if df is None:
            return {"error": f"No data found for {symbol}. Check if the ticker is valid on PSX.", "verdict": {}, "computation_log": []}

        if len(df) < 20:
            return {"error": f"Insufficient data for {symbol} — only {len(df)} bars (need 20+).", "verdict": {}, "computation_log": []}

        company_name, sector = _get_company_info(symbol)

        # Basic info
        price = round(float(df["Close"].iloc[-1]), 2)
        change = round(float(live_bar["change"]), 2) if live_bar else 0
        change_pct = round(change / float(live_bar["ldcp"]) * 100, 2) if live_bar and live_bar.get("ldcp", 0) > 0 else 0
        volume = int(df["Volume"].iloc[-1])

        # --- LOG: Raw Data ---
        log.section("STEP 1: RAW DATA FROM PSX + YFINANCE")
        log.kv("Symbol", symbol)
        log.kv("Company", company_name)
        log.kv("Sector", sector)
        log.kv("Bars fetched", len(df))
        log.kv("Date range", f"{df.index[0].date()} to {df.index[-1].date()}")
        log.kv("PSX live bar", "Yes" if live_bar else "No (PSX unavailable)")
        log.blank()

        if live_bar:
            log.subsection("PSX Live Bar (today)")
            log.kv("Open", live_bar.get("open"))
            log.kv("High", live_bar.get("high"))
            log.kv("Low", live_bar.get("low"))
            log.kv("Close", live_bar.get("close"))
            log.kv("Volume", live_bar.get("volume"))
            log.kv("LDCP (prev close)", live_bar.get("ldcp"))
            log.kv("Change", live_bar.get("change"))

        log.subsection("Last 10 OHLCV Bars")
        log.text(f"  {'Date':>12s}  {'Open':>10s}  {'High':>10s}  {'Low':>10s}  {'Close':>10s}  {'Volume':>12s}")
        log.text("  " + "-" * 70)
        for idx, row in df.tail(10).iterrows():
            dt = idx.date() if hasattr(idx, 'date') else str(idx)[:10]
            log.text(f"  {str(dt):>12s}  {row['Open']:>10.2f}  {row['High']:>10.2f}  {row['Low']:>10.2f}  {row['Close']:>10.2f}  {int(row['Volume']):>12,}")

        # =====================================================================
        # STEP 2: TECHNICAL ANALYSIS (17 techniques)
        # =====================================================================
        if progress_callback:
            progress_callback("step", f"Running 17 technical techniques on {symbol}...")

        log_entries = run_deep_analysis(df, live_bar)

        confluence = log_entries[-1]
        technique_logs = log_entries[:-1]

        if progress_callback:
            bullish = confluence["values"]["bullish_count"]
            bearish = confluence["values"]["bearish_count"]
            progress_callback("step", f"Techniques complete: {bullish} bullish, {bearish} bearish signals")

        # --- LOG: Each technique result ---
        log.section("STEP 2: TECHNICAL ANALYSIS — 17 TECHNIQUES")

        for entry in technique_logs:
            signal = entry["signal"]
            icon = {"BULLISH": "[+]", "BEARISH": "[-]", "NEUTRAL": "[~]"}[signal]
            log.text(f"{icon} {signal:8s} | {entry['name']}")
            log.text(f"           Reason: {entry['reason']}")
            vals = entry.get("values", {})
            if vals:
                for k, v in vals.items():
                    if isinstance(v, dict):
                        for kk, vv in v.items():
                            log.text(f"           {k}.{kk}: {vv}")
                    elif isinstance(v, list):
                        log.text(f"           {k}: {', '.join(str(x) for x in v)}")
                    else:
                        log.text(f"           {k}: {v}")
            log.blank()

        # --- LOG: Confluence ---
        log.subsection("CONFLUENCE SUMMARY")
        cv = confluence["values"]
        log.kv("Bullish signals", f"{cv['bullish_count']} / {cv['total']}")
        log.kv("Bearish signals", f"{cv['bearish_count']} / {cv['total']}")
        log.kv("Neutral signals", f"{cv['neutral_count']} / {cv['total']}")
        log.kv("Overall", confluence["signal"])
        log.kv("Summary", confluence["reason"])

        # =====================================================================
        # STEP 3: AI PROMPTS SENT
        # =====================================================================
        computation_log_text = format_log_for_ai(log_entries)
        confluence_text = f"{cv['score_text']} — {confluence['reason']}"

        log.section("STEP 3: AI PROMPTS SENT")
        # The prompts are constructed inside run_deep_analysis_ai, but we log
        # the data we're sending so the user can see exactly what the AI received.
        log.subsection("Data sent to AI — Computation Log")
        log.text(computation_log_text)
        log.blank()
        log.subsection("Data sent to AI — Confluence Summary")
        log.text(confluence_text)

        # =====================================================================
        # STEP 4: AI RESPONSE
        # =====================================================================
        if progress_callback:
            progress_callback("step", f"Sending to AI ({provider}) — News Scout + Senior Analyst...")

        raw_output = run_deep_analysis_ai(
            symbol=symbol,
            company_name=company_name,
            sector=sector,
            computation_log=computation_log_text,
            confluence_text=confluence_text,
            provider=provider,
            api_key=api_key,
            progress_callback=progress_callback,
        )

        if progress_callback:
            progress_callback("step", "Parsing AI verdict...")

        log.section("STEP 4: AI RESPONSE (RAW)")
        log.text(raw_output)

        # =====================================================================
        # STEP 5: PARSED VERDICT
        # =====================================================================
        verdict = parse_verdict(raw_output)

        log.section("STEP 5: PARSED VERDICT")
        for k, v in verdict.items():
            if isinstance(v, list):
                log.kv(k, ", ".join(str(x) for x in v))
            else:
                log.kv(k, v)

        # Save the complete log
        log_path = log.save()
        if progress_callback:
            progress_callback("step", f"Full analysis log saved to {log_path.name}")

        return {
            "symbol": symbol,
            "company_name": company_name,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "basic_technicals": compute_technicals(df),
            "computation_log": format_log_for_display(log_entries),
            "confluence": confluence["values"],
            "verdict": verdict,
            "raw_output": raw_output,
            "log_path": str(log_path),
            "error": None,
        }

    except Exception as e:
        # Still save what we have
        log.section("ERROR")
        log.text(str(e))
        try:
            log_path = log.save()
        except Exception:
            log_path = None

        return {
            "error": str(e),
            "verdict": {},
            "computation_log": [],
            "raw_output": "",
            "log_path": str(log_path) if log_path else None,
        }
