import streamlit as st
import os
from dotenv import load_dotenv
from scanner import run_scan
from data import cache_info
from mock_data import get_mock_result
from datetime import datetime

load_dotenv()

st.set_page_config(
    page_title="PSX AI Scanner",
    page_icon="📈",
    layout="wide",
)

# --- Styles ---
st.markdown("""
<style>
    .pick-card { background: #1e1e2e; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid #2e2e4e; }
    .rank-badge { background: #0C447C; color: white; border-radius: 50%; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; font-size: 14px; }
    .rank-top { background: #16a34a; }
    .signal-tag { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; margin: 2px; background: #1d4ed8; color: white; }
    .grid-label { color: #94a3b8; font-size: 12px; font-weight: 500; }
    .grid-value { color: #f1f5f9; font-size: 15px; font-weight: 600; }
    .stoploss-val { color: #ef4444; }
    .target-val { color: #22c55e; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.title("📈 PSX AI Scanner")
st.caption("Shariah-compliant T+1 & Swing trade picks — powered by AI analysis on real market data")

# --- Sidebar: Settings ---
with st.sidebar:
    st.header("⚙️ Settings")

    provider = st.selectbox(
        "AI Provider",
        options=["gemini", "groq", "openai"],
        format_func=lambda x: {
            "gemini": "Google Gemini (Free)",
            "groq": "Groq — Llama 3.3 70b (Free, Fast)",
            "openai": "OpenAI GPT-4o Mini",
        }.get(x, x),
    )

    default_key = {
        "gemini": os.getenv("GEMINI_API_KEY", ""),
        "groq": os.getenv("GROQ_API_KEY", ""),
        "openai": os.getenv("OPENAI_API_KEY", ""),
    }.get(provider, "")
    api_key = st.text_input(
        "API Key",
        value=default_key,
        type="password",
        help="Enter your API key. For Gemini, get one free at aistudio.google.com",
    )

    st.divider()
    st.header("🔧 Scan Filters")

    trade_style = st.radio(
        "Trade Style",
        options=["T+1", "Swing 3-5d"],
        horizontal=True,
    )

    risk_level = st.radio(
        "Risk Level",
        options=["Conservative", "Moderate", "Aggressive"],
        horizontal=True,
        index=1,
    )

    st.divider()
    mock_mode = st.toggle("Mock Mode (no API calls)", value=False, help="Use sample data for UI testing — no yfinance, no AI")
    use_ai_data = st.toggle("AI Data Mode", value=False, help="Use the selected AI provider to fetch PSX stock data instead of yfinance. Same provider used for agents.", disabled=mock_mode)
    force_refresh = st.toggle("Force Refresh (ignore cache)", value=False, help="Re-fetch fresh data from yfinance even if today's cache exists.", disabled=mock_mode or use_ai_data)

    _ci = cache_info()
    if _ci:
        st.caption(f"💾 Cache: {_ci['rows']} stocks, saved {_ci['saved_at']}")
        if _ci.get("data_as_of"):
            if _ci.get("is_stale"):
                st.caption(f"⚠️ Data as of {_ci['data_as_of']} (expected {_ci['expected_trading_day']})")
            else:
                st.caption(f"📅 Data as of {_ci['data_as_of']}")
    else:
        st.caption("💾 Cache: empty for today")

    st.divider()
    st.caption("Stock Universe: Top 100 KMI All Shares (Shariah compliant)")
    st.caption("Data: PSX live (dps.psx.com.pk) + yfinance history")
    st.caption("Not financial advice.")


# --- Session state ---
if "scan_result" not in st.session_state:
    st.session_state.scan_result = None
if "scan_time" not in st.session_state:
    st.session_state.scan_time = None
if "scanning" not in st.session_state:
    st.session_state.scanning = False
if "scan_error" not in st.session_state:
    st.session_state.scan_error = None
if "scan_log" not in st.session_state:
    st.session_state.scan_log = []


# --- Mode banners ---
if mock_mode:
    st.info("🧪 **Mock Mode ON** — Using sample data. No API calls or AI will be made.", icon="🧪")
elif use_ai_data:
    st.info(f"🔍 **AI Data Mode ON** — {provider.title()} will fetch PSX stock data. All analysis also uses {provider.title()}.", icon="🔍")

# --- Scan button ---
col1, col2 = st.columns([2, 1])
with col1:
    btn_label = f"🧪 Load Mock Data ({trade_style})" if mock_mode else f"🔍 Scan KMI Top 100 Now ({trade_style})"
    scan_clicked = st.button(
        btn_label,
        type="primary",
        use_container_width=True,
        disabled=st.session_state.scanning,
    )
with col2:
    if st.session_state.scan_result:
        if st.button("🔄 New Scan", use_container_width=True):
            st.session_state.scan_result = None
            st.session_state.scan_time = None
            st.rerun()


# --- Run scan ---
if scan_clicked:
    if not mock_mode and not api_key:
        st.error("Please enter your API key in the sidebar.")
    else:
        st.session_state.scanning = True

        log_placeholder = st.empty()
        log_lines = []

        def render_log():
            log_html = "".join([
                f"<div style='color:{'#facc15' if '⚠️' in l else '#6ee7b7' if '✅' in l else '#ef4444' if 'ERROR' in l else '#93c5fd'};font-size:12px;font-family:monospace;padding:1px 0'>{l}</div>"
                for l in log_lines
            ])
            log_placeholder.markdown(
                f"<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;height:200px;overflow-y:auto'>{log_html}</div>",
                unsafe_allow_html=True,
            )

        if mock_mode:
            log_lines.append("🧪 Mock mode enabled — skipping all API calls")
            render_log()
            result = get_mock_result(trade_style=trade_style, risk_level=risk_level)
            log_lines.append(f"✅ Loaded {result['stocks_scanned']} mock stocks and {len(result['picks'])} picks")
            render_log()
        else:
            def progress_callback(msg_type, msg):
                if msg_type == "step":
                    log_lines.append(f"🔵 {msg}")
                elif msg_type == "skip":
                    log_lines.append(f"⚠️ {msg}")
                else:
                    log_lines.append(f"⚙️ {msg}")
                render_log()

            result = run_scan(
                trade_style=trade_style,
                risk_level=risk_level,
                provider=provider,
                api_key=api_key,
                use_ai_data=use_ai_data,
                force_refresh=force_refresh,
                progress_callback=progress_callback,
            )

        st.session_state.scanning = False
        st.session_state.scan_log = log_lines.copy()
        log_placeholder.empty()  # clear live log — it moves to the scan log expander

        if result["error"]:
            print(f"[SCAN ERROR] {result['error']}")
            st.session_state.scan_error = result["error"]
        else:
            st.session_state.scan_error = None
            import time
            for i in range(5, 0, -1):
                log_lines.append(f"⏳ Showing results in {i}...")
                render_log()
                time.sleep(1)
            st.session_state.scan_result = result
            st.session_state.scan_time = datetime.now().strftime("%d-%b-%Y, %I:%M %p")
            st.rerun()


# --- Persistent error display ---
if st.session_state.scan_error:
    st.error(f"**Scan failed:** {st.session_state.scan_error}")
    if st.button("Dismiss"):
        st.session_state.scan_error = None
        st.rerun()

# --- Collapsible scan log ---
if st.session_state.scan_log:
    with st.expander("📋 Scan Log", expanded=False):
        log_html = "".join([
            f"<div style='color:{'#facc15' if '⚠️' in l else '#6ee7b7' if '✅' in l else '#ef4444' if 'ERROR' in l else '#93c5fd'};font-size:12px;font-family:monospace;padding:1px 0'>{l}</div>"
            for l in st.session_state.scan_log
        ])
        st.markdown(
            f"<div style='background:#0f172a;border-radius:6px;padding:12px;max-height:300px;overflow-y:auto'>{log_html}</div>",
            unsafe_allow_html=True,
        )

# --- Results ---
if st.session_state.scan_result:
    result = st.session_state.scan_result
    picks = result.get("picks", [])

    st.divider()

    # Freshness banner — critical: if yfinance is behind, picks are based on stale prices.
    _ci_after = cache_info()
    if _ci_after and _ci_after.get("is_stale"):
        st.error(
            f"⚠️ **Stale data warning** — picks are based on prices from **{_ci_after['data_as_of']}**, "
            f"but the expected trading day is **{_ci_after['expected_trading_day']}**. "
            f"Yahoo's PSX feed is behind. Today's moves are NOT reflected in these picks. "
            f"Cross-check each pick against a live quote before acting.",
            icon="⚠️",
        )

    # Summary bar
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stocks Scanned", result["stocks_scanned"])
    col2.metric("Top Picks Found", len(picks))
    col3.metric("Scanned At", st.session_state.scan_time)
    col4.metric("Data As Of", _ci_after.get("data_as_of", "—") if _ci_after else "—")

    st.divider()

    if not picks:
        st.warning("No picks were parsed from the AI output. See raw output below.")
    else:
        st.subheader(f"🏆 Top {len(picks)} Picks — {trade_style} | {risk_level} Risk")

        for pick in picks:
            rank = pick.get("rank", "?")
            symbol = pick.get("symbol", "?")
            is_top3 = isinstance(rank, int) and rank <= 3

            with st.expander(f"{'🥇' if rank == 1 else '🥈' if rank == 2 else '🥉' if rank == 3 else f'#{rank}'} {symbol} — {pick.get('price', '')}  |  {pick.get('buy_range', '')}  →  SL: {pick.get('stoploss', '')}  |  R:R {pick.get('rr', '')}"):

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown('<p class="grid-label">BUY RANGE</p>', unsafe_allow_html=True)
                    st.markdown(f'<p class="grid-value target-val">{pick.get("buy_range", "—")}</p>', unsafe_allow_html=True)
                with col2:
                    st.markdown('<p class="grid-label">TARGET 1</p>', unsafe_allow_html=True)
                    st.markdown(f'<p class="grid-value target-val">{pick.get("target1", "—")}</p>', unsafe_allow_html=True)
                with col3:
                    st.markdown('<p class="grid-label">TARGET 2</p>', unsafe_allow_html=True)
                    st.markdown(f'<p class="grid-value target-val">{pick.get("target2", "—")}</p>', unsafe_allow_html=True)
                with col4:
                    st.markdown('<p class="grid-label">STOPLOSS</p>', unsafe_allow_html=True)
                    st.markdown(f'<p class="grid-value stoploss-val">{pick.get("stoploss", "—")}</p>', unsafe_allow_html=True)

                col5, col6 = st.columns(2)
                with col5:
                    st.markdown('<p class="grid-label">RISK:REWARD</p>', unsafe_allow_html=True)
                    st.markdown(f'<p class="grid-value">{pick.get("rr", "—")}</p>', unsafe_allow_html=True)
                with col6:
                    st.markdown('<p class="grid-label">HOLD PERIOD</p>', unsafe_allow_html=True)
                    st.markdown(f'<p class="grid-value">{pick.get("hold", "—")}</p>', unsafe_allow_html=True)

                if pick.get("signals"):
                    st.markdown(" ".join([f'<span class="signal-tag">{s}</span>' for s in pick["signals"]]), unsafe_allow_html=True)

                if pick.get("reasoning"):
                    st.caption(pick["reasoning"])

    # Share picks
    st.divider()
    with st.expander("📤 Share Picks (WhatsApp Format)"):
        if picks:
            share_text = f"*PSX AI Scanner — {trade_style} Picks*\n"
            share_text += f"_{st.session_state.scan_time}_\n"
            share_text += f"_{risk_level} Risk | {result['stocks_scanned']} stocks scanned_\n\n"
            for pick in picks:
                share_text += f"*{pick.get('rank', '?')}. {pick.get('symbol', '?')}* @ {pick.get('price', '')}\n"
                share_text += f"  Buy: {pick.get('buy_range', '—')}\n"
                share_text += f"  T1: {pick.get('target1', '—')}  T2: {pick.get('target2', '—')}\n"
                share_text += f"  SL: {pick.get('stoploss', '—')}  R:R {pick.get('rr', '—')}\n\n"
            share_text += "_Not financial advice. DYOR._"
            st.text_area("Copy this:", value=share_text, height=300, key="share_text_area")
            escaped = share_text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
            st.components.v1.html(f"""
<button id="copybtn" onclick="navigator.clipboard.writeText(`{escaped}`).then(() => {{ document.getElementById('copybtn').innerText = '✅ Copied!'; }}).catch(() => {{ document.getElementById('copybtn').innerText = '❌ Failed'; }})"
    style="background:#0C447C;color:white;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-size:14px;margin-top:4px">
    📋 Copy to Clipboard
</button>
""", height=50)

    # Raw output toggle
    with st.expander("🔍 Raw AI Output"):
        st.text(result.get("raw_output", ""))
