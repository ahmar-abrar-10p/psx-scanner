import streamlit as st
import os
from dotenv import load_dotenv
from scanner import run_scan
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
        options=["gemini", "openai"],
        format_func=lambda x: {"gemini": "Google Gemini (Free)", "openai": "OpenAI GPT-4o Mini"}.get(x, x),
    )

    default_key = os.getenv("GEMINI_API_KEY", "") if provider == "gemini" else os.getenv("OPENAI_API_KEY", "")
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
    st.caption("Stock Universe: Top 100 KMI All Shares (Shariah compliant)")
    st.caption("Data: PSX end-of-day via yfinance")
    st.caption("Not financial advice.")


# --- Session state ---
if "scan_result" not in st.session_state:
    st.session_state.scan_result = None
if "scan_time" not in st.session_state:
    st.session_state.scan_time = None
if "scanning" not in st.session_state:
    st.session_state.scanning = False


# --- Scan button ---
col1, col2 = st.columns([2, 1])
with col1:
    scan_clicked = st.button(
        f"🔍 Scan KMI Top 100 Now ({trade_style})",
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
    if not api_key:
        st.error("Please enter your API key in the sidebar.")
    else:
        st.session_state.scanning = True
        progress_container = st.container()

        with progress_container:
            status = st.status("Running scan...", expanded=True)
            log_lines = []

            def progress_callback(msg_type, msg):
                log_lines.append(msg)
                status.write(f"{'🔵' if msg_type == 'step' else '⚙️'} {msg}")

            result = run_scan(
                trade_style=trade_style,
                risk_level=risk_level,
                provider=provider,
                api_key=api_key,
                progress_callback=progress_callback,
            )

            if result["error"]:
                status.update(label="Scan failed", state="error")
                st.error(f"Error: {result['error']}")
            else:
                status.update(label=f"Scan complete — {result['stocks_scanned']} stocks analyzed", state="complete")
                st.session_state.scan_result = result
                st.session_state.scan_time = datetime.now().strftime("%d-%b-%Y, %I:%M %p")

        st.session_state.scanning = False
        st.rerun()


# --- Results ---
if st.session_state.scan_result:
    result = st.session_state.scan_result
    picks = result.get("picks", [])

    st.divider()

    # Summary bar
    col1, col2, col3 = st.columns(3)
    col1.metric("Stocks Scanned", result["stocks_scanned"])
    col2.metric("Top Picks Found", len(picks))
    col3.metric("Scanned At", st.session_state.scan_time)

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
            st.text_area("Copy this:", value=share_text, height=300)
            st.button("📋 Copy to Clipboard", on_click=lambda: st.write("Copied!"))

    # Raw output toggle
    with st.expander("🔍 Raw AI Output"):
        st.text(result.get("raw_output", ""))
