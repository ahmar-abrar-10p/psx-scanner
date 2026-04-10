import streamlit as st
import os
from dotenv import load_dotenv
from analyzer import run_single_stock_analysis
from data import load_universe
from ohlcv_store import store_stats
from datetime import datetime

load_dotenv()

# --- Styles ---
st.markdown("""
<style>
    .verdict-buy { background: #16a34a; color: white; padding: 16px 32px; border-radius: 12px;
                   font-size: 28px; font-weight: bold; text-align: center; }
    .verdict-avoid { background: #dc2626; color: white; padding: 16px 32px; border-radius: 12px;
                     font-size: 28px; font-weight: bold; text-align: center; }
    .verdict-wait { background: #d97706; color: white; padding: 16px 32px; border-radius: 12px;
                    font-size: 28px; font-weight: bold; text-align: center; }
    .signal-bullish { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px;
                      font-weight: 500; margin: 2px; background: #16a34a; color: white; }
    .signal-bearish { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px;
                      font-weight: 500; margin: 2px; background: #dc2626; color: white; }
    .signal-neutral { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px;
                      font-weight: 500; margin: 2px; background: #6b7280; color: white; }
    .level-label { color: #94a3b8; font-size: 12px; font-weight: 500; }
    .level-value { font-size: 15px; font-weight: 600; color: #3b82f6; }
    .target-val { color: #22c55e !important; }
    .stoploss-val { color: #ef4444 !important; }
    /* Force ticker input to show uppercase */
    input[aria-label="Enter PSX Ticker"] { text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.title("🔬 PSX Stock Analyzer")
st.caption("Deep multi-technique analysis — 17 indicators + AI verdict for any PSX stock")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Settings")

    provider = st.selectbox(
        "AI Provider",
        options=["ollama", "gemini", "groq", "openai"],
        format_func=lambda x: {
            "ollama": "Ollama — Local (Free, No API key)",
            "gemini": "Google Gemini (Free)",
            "groq": "Groq — Llama 3.3 70b (Free, Fast)",
            "openai": "OpenAI GPT-4o Mini",
        }.get(x, x),
        key="analyzer_provider",
    )

    default_key = {
        "ollama": "not-needed",
        "gemini": os.getenv("GEMINI_API_KEY", ""),
        "groq": os.getenv("GROQ_API_KEY", ""),
        "openai": os.getenv("OPENAI_API_KEY", ""),
    }.get(provider, "")
    api_key = st.text_input(
        "API Key",
        value=default_key,
        type="password",
        help="Enter your API key for the selected provider",
        key="analyzer_api_key",
    )

    st.divider()
    st.caption("Analysis: 17 technical techniques + AI synthesis")
    st.caption("Data: Sarmaaya API (live) + OHLCV store (history)")
    st.caption("Not financial advice.")

# --- Load universe for autocomplete ---
kmi_symbols = load_universe()

# --- Pre-check: OHLCV store ---
_store_ready = store_stats()["count"] > 0
if not _store_ready:
    st.warning("No OHLCV history found. Go to **KMI Scanner** page and click **Generate History** to download stock data first.")

# --- Input ---
col_input, col_btn = st.columns([3, 1])
with col_input:
    symbol = st.text_input(
        "Enter PSX Ticker",
        placeholder="e.g. OGDC, LUCK, HBL, MEBL",
        help=f"Enter any PSX ticker. KMI stocks: {', '.join(kmi_symbols[:10])}...",
    ).strip().upper()

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button("🔬 Analyze", type="primary", use_container_width=True, disabled=not _store_ready)

# --- Session state ---
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "analysis_time" not in st.session_state:
    st.session_state.analysis_time = None

# --- Run analysis ---
if analyze_clicked:
    if not symbol:
        st.error("Please enter a ticker symbol.")
    elif not api_key:
        st.error("Please enter your API key in the sidebar.")
    else:
        # Clear previous result immediately
        st.session_state.analysis_result = None
        st.session_state.analysis_time = None

        log_placeholder = st.empty()
        log_lines = []

        def render_log():
            log_html = "".join([
                f"<div style='color:{'#facc15' if 'STALE' in l or 'WARN' in l else '#6ee7b7' if 'FRESH' in l or 'complete' in l.lower() else '#ef4444' if 'ERROR' in l else '#93c5fd'};font-size:12px;font-family:monospace;padding:1px 0'>{l}</div>"
                for l in log_lines
            ])
            log_placeholder.markdown(
                f"<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;max-height:300px;overflow-y:auto'>{log_html}</div>",
                unsafe_allow_html=True,
            )

        def progress_callback(msg_type, msg):
            if msg_type == "step":
                log_lines.append(f"🔵 {msg}")
            elif msg_type == "fetch":
                log_lines.append(f"⚙️ {msg}")
            else:
                log_lines.append(f"⚙️ {msg}")
            render_log()

        result = run_single_stock_analysis(
            symbol=symbol,
            provider=provider,
            api_key=api_key,
            progress_callback=progress_callback,
        )

        log_placeholder.empty()

        if result.get("error"):
            st.error(f"**Analysis failed:** {result['error']}")
        else:
            st.session_state.analysis_result = result
            st.session_state.analysis_time = datetime.now().strftime("%d-%b-%Y, %I:%M %p")
            st.rerun()

# --- Results ---
if st.session_state.analysis_result:
    result = st.session_state.analysis_result
    verdict = result.get("verdict", {})

    st.divider()

    # Stock header
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Symbol", f"{result['symbol']}")
    col2.metric("Price", f"Rs {result['price']}")
    change_prefix = "+" if result.get("change_pct", 0) > 0 else ""
    col3.metric("Change", f"{change_prefix}{result.get('change_pct', 0)}%", delta=f"{result.get('change', 0)}")
    col4.metric("Volume", f"{result.get('volume', 0):,}")

    if result.get("company_name"):
        st.caption(result["company_name"])

    st.divider()

    # --- Verdict Card ---
    verdict_text = verdict.get("verdict", "UNKNOWN")
    if "BUY" in verdict_text.upper():
        st.markdown(f'<div class="verdict-buy">✅ BUY — Conviction {verdict.get("conviction", "?")} / 10</div>', unsafe_allow_html=True)
    elif "AVOID" in verdict_text.upper():
        st.markdown(f'<div class="verdict-avoid">🚫 AVOID — Conviction {verdict.get("conviction", "?")} / 10</div>', unsafe_allow_html=True)
    elif "WAIT" in verdict_text.upper():
        st.markdown(f'<div class="verdict-wait">⏸️ WAIT — Conviction {verdict.get("conviction", "?")} / 10</div>', unsafe_allow_html=True)
    else:
        st.info(f"Verdict: {verdict_text}")

    st.markdown("")

    # Timeframe
    if verdict.get("timeframe"):
        st.markdown(f"**Suggested Timeframe:** {verdict['timeframe']}")

    # Price levels
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<p class="level-label">ENTRY</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="level-value">{verdict.get("entry", "—")}</p>', unsafe_allow_html=True)
    with col2:
        st.markdown('<p class="level-label">STOPLOSS</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="level-value stoploss-val">{verdict.get("stoploss", "—")}</p>', unsafe_allow_html=True)
    with col3:
        st.markdown('<p class="level-label">TARGET 1</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="level-value target-val">{verdict.get("target1", "—")}</p>', unsafe_allow_html=True)
    with col4:
        st.markdown('<p class="level-label">TARGET 2</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="level-value target-val">{verdict.get("target2", "—")}</p>', unsafe_allow_html=True)

    col5, col6 = st.columns(2)
    with col5:
        st.markdown(f"**Risk:Reward:** {verdict.get('risk_reward', '—')}")
    with col6:
        st.markdown(f"**Analyzed at:** {st.session_state.analysis_time}")

    # Reasoning
    if verdict.get("reasoning"):
        st.markdown(f"**Reasoning:** {verdict['reasoning']}")

    # News impact
    if verdict.get("news_impact"):
        st.markdown(f"**News Impact:** {verdict['news_impact']}")

    # Signal tags
    st.markdown("")
    bullish = verdict.get("bullish_signals", [])
    bearish = verdict.get("bearish_signals", [])
    if bullish:
        tags = " ".join([f'<span class="signal-bullish">{s}</span>' for s in bullish])
        st.markdown(f"**Bullish:** {tags}", unsafe_allow_html=True)
    if bearish:
        tags = " ".join([f'<span class="signal-bearish">{s}</span>' for s in bearish])
        st.markdown(f"**Bearish:** {tags}", unsafe_allow_html=True)

    # Conflicts
    if verdict.get("conflicts") and verdict["conflicts"].lower() != "none":
        st.warning(f"**Conflicts:** {verdict['conflicts']}")

    st.divider()

    # --- Confluence Summary ---
    confluence = result.get("confluence", {})
    if confluence:
        bullish_count = confluence.get("bullish_count", 0)
        bearish_count = confluence.get("bearish_count", 0)
        total = confluence.get("total", 17)
        st.subheader("📊 Signal Confluence")
        col1, col2, col3 = st.columns(3)
        col1.metric("Bullish", f"{bullish_count} / {total}")
        col2.metric("Bearish", f"{bearish_count} / {total}")
        col3.metric("Neutral", f"{confluence.get('neutral_count', 0)} / {total}")

        # Visual bar
        if bullish_count + bearish_count > 0:
            ratio = bullish_count / (bullish_count + bearish_count)
            st.progress(ratio, text=f"{bullish_count} bullish vs {bearish_count} bearish")

    # --- Computation Log ---
    with st.expander("📋 Computation Log (17 Techniques)", expanded=False):
        log_data = result.get("computation_log", [])
        if log_data:
            # Color-code the signal column
            for row in log_data:
                signal = row["Signal"]
                if signal == "BULLISH":
                    row["Signal"] = "🟢 BULLISH"
                elif signal == "BEARISH":
                    row["Signal"] = "🔴 BEARISH"
                else:
                    row["Signal"] = "⚪ NEUTRAL"

            import pandas as pd
            df_log = pd.DataFrame(log_data)
            st.dataframe(df_log, width="stretch", hide_index=True)

    # --- Raw AI Output ---
    with st.expander("🔍 Raw AI Output"):
        st.text(result.get("raw_output", ""))

    # --- New Analysis button ---
    if st.button("🔬 New Analysis", use_container_width=True):
        st.session_state.analysis_result = None
        st.session_state.analysis_time = None
        st.rerun()
