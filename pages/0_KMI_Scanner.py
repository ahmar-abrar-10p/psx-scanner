import streamlit as st
import os
from dotenv import load_dotenv
from scanner import run_scan
from data import load_universe, fetch_live_data
from ohlcv_store import backfill_all, store_stats, _make_session, save_ohlcv, load_ohlcv, _last_psx_trading_day
from mock_data import get_mock_result
from datetime import datetime

load_dotenv()

# --- Styles ---
st.markdown("""
<style>
    .pick-card { background: #1e1e2e; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid #2e2e4e; }
    .rank-badge { background: #0C447C; color: white; border-radius: 50%; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; font-size: 14px; }
    .rank-top { background: #16a34a; }
    .signal-tag { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; margin: 2px; background: #1d4ed8; color: white; }
    .grid-label { color: #94a3b8; font-size: 12px; font-weight: 500; }
    .grid-value { font-size: 15px; font-weight: 600; color: #3b82f6; }
    .stoploss-val { color: #ef4444 !important; }
    .target-val { color: #22c55e !important; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.title("📈 PSX KMI Scanner")
st.caption("Shariah-compliant T+1 & Swing trade picks — powered by AI analysis on real market data")

# --- Sidebar: Settings ---
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
        key="scanner_provider",
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
        help="Enter your API key. For Gemini, get one free at aistudio.google.com",
        key="scanner_api_key",
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

    # --- OHLCV History Store ---
    st.divider()
    st.header("📦 OHLCV History")
    _stats = store_stats()
    if _stats["count"] > 0:
        st.caption(f"📊 {_stats['count']} stocks stored ({_stats['total_size_kb']} KB)")
        st.caption(f"📅 {_stats['oldest']} -> {_stats['newest']}")
    else:
        st.caption("📊 No history stored yet")

    col_hist, col_refresh = st.columns(2)
    with col_hist:
        if st.button(
            "Generate History" if _stats["count"] == 0 else "Rebuild History",
            help="Download 6 months of OHLCV history for all KMI stocks from Yahoo Finance. "
                 "Deletes existing history and re-fetches fresh data.",
            use_container_width=True,
            key="generate_history_btn",
        ):
            st.session_state.generating_history = True
            st.rerun()

    with col_refresh:
        if st.button(
            "Refresh Today",
            help="Fetch today's live prices from Sarmaaya API and update OHLCV store. "
                 "Use during or after market hours to get latest data.",
            use_container_width=True,
            key="refresh_today_btn",
            disabled=_stats["count"] == 0,
        ):
            st.session_state.refreshing_today = True
            st.rerun()

    st.divider()
    st.caption("Stock Universe: KMI All Shares (Shariah compliant)")
    st.caption("Data: Sarmaaya API (live) + OHLCV store (history)")
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
if "generating_history" not in st.session_state:
    st.session_state.generating_history = False
if "refreshing_today" not in st.session_state:
    st.session_state.refreshing_today = False


# --- Refresh Today ---
if st.session_state.refreshing_today:
    st.info("Fetching today's live prices from Sarmaaya API...")
    with st.spinner("Updating OHLCV store with today's data..."):
        live_data = fetch_live_data()
        if live_data:
            symbols = load_universe()
            today = _last_psx_trading_day()
            updated = 0
            for sym in symbols:
                if sym not in live_data:
                    continue
                bar = live_data[sym]
                if bar["close"] <= 0:
                    continue
                existing = load_ohlcv(sym)
                if existing is None:
                    continue
                import pandas as _pd
                today_ts = _pd.Timestamp(today)
                live_row = _pd.DataFrame(
                    [{"Open": bar["open"], "High": bar["high"], "Low": bar["low"],
                      "Close": bar["close"], "Volume": bar["volume"]}],
                    index=_pd.DatetimeIndex([today_ts]),
                )
                # Remove existing today row if present, then append fresh
                df = existing[existing.index.date < today]
                df = _pd.concat([df, live_row])
                save_ohlcv(sym, df)
                updated += 1
            st.success(f"Updated {updated} stocks with today's live data.")
        else:
            st.error("Failed to fetch live data from Sarmaaya API.")
    st.session_state.refreshing_today = False
    import time as _time
    _time.sleep(2)
    st.rerun()


# --- Generate History ---
if st.session_state.generating_history:
    st.info("📦 **Generating OHLCV History** — downloading 6 months of data for all KMI stocks...")
    progress_bar = st.progress(0, text="Starting...")
    log_placeholder = st.empty()
    log_lines = []

    def render_history_log():
        log_html = "".join([
            f"<div style='color:{'#facc15' if 'SKIP' in l or 'WARN' in l else '#6ee7b7' if 'complete' in l.lower() or 'ready' in l.lower() else '#ef4444' if 'ERROR' in l else '#93c5fd'};font-size:12px;font-family:monospace;padding:1px 0'>{l}</div>"
            for l in log_lines[-20:]
        ])
        log_placeholder.markdown(
            f"<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;max-height:200px;overflow-y:auto'>{log_html}</div>",
            unsafe_allow_html=True,
        )

    def history_progress(msg, current, total):
        log_lines.append(f"⚙️ {msg}")
        render_history_log()
        if total > 0:
            progress_bar.progress(min(current / total, 1.0), text=msg[:80])

    symbols = load_universe()
    session = _make_session()
    result = backfill_all(symbols, session=session, progress_callback=history_progress)

    st.session_state.generating_history = False
    stats = store_stats()
    progress_bar.progress(1.0, text=f"Done! {stats['count']} stocks stored.")
    st.success(f"History generated: {stats['count']} stocks, {stats['total_size_kb']} KB, {stats['oldest']} -> {stats['newest']}")
    import time as _time
    _time.sleep(3)
    st.rerun()


# --- Mode banners ---
if mock_mode:
    st.info("🧪 **Mock Mode ON** — Using sample data. No API calls or AI will be made.", icon="🧪")
elif use_ai_data:
    st.info(f"🔍 **AI Data Mode ON** — {provider.title()} will fetch PSX stock data. All analysis also uses {provider.title()}.", icon="🔍")

# --- Pre-check: OHLCV store ---
_store_ready = store_stats()["count"] > 0
if not _store_ready and not mock_mode:
    st.warning("No OHLCV history found. Click **Generate History** in the sidebar to download stock data before scanning.")

# --- Scan button ---
col1, col2 = st.columns([2, 1])
with col1:
    btn_label = f"🧪 Load Mock Data ({trade_style})" if mock_mode else f"🔍 Scan KMI Stocks Now ({trade_style})"
    scan_clicked = st.button(
        btn_label,
        type="primary",
        use_container_width=True,
        disabled=st.session_state.scanning or (not _store_ready and not mock_mode),
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
                progress_callback=progress_callback,
            )

        st.session_state.scanning = False
        st.session_state.scan_log = log_lines.copy()
        log_placeholder.empty()

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
