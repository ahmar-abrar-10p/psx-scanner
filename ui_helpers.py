"""
ui_helpers.py — Shared Streamlit UI components used across pages.
"""
import os
import streamlit as st


# --- Provider constants ---
PROVIDERS = ["ollama", "gemini", "groq", "openai"]

PROVIDER_LABELS = {
    "ollama": "Ollama -- Local (Free, No API key)",
    "gemini": "Google Gemini (Free)",
    "groq": "Groq -- Llama 3.3 70b (Free, Fast)",
    "openai": "OpenAI GPT-4o Mini",
}

PROVIDER_ENV_KEYS = {
    "ollama": "not-needed",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def render_provider_sidebar(key_prefix: str) -> tuple[str, str]:
    """
    Render the AI provider selectbox and API key input in the sidebar.
    Returns (provider, api_key).
    key_prefix: unique prefix for Streamlit widget keys (e.g. "scanner", "analyzer").
    """
    provider = st.selectbox(
        "AI Provider",
        options=PROVIDERS,
        format_func=lambda x: PROVIDER_LABELS.get(x, x),
        key=f"{key_prefix}_provider",
    )

    env_key = PROVIDER_ENV_KEYS.get(provider, "")
    default_key = env_key if env_key == "not-needed" else os.getenv(env_key, "")
    api_key = st.text_input(
        "API Key",
        value=default_key,
        type="password",
        help="Enter your API key for the selected provider",
        key=f"{key_prefix}_api_key",
    )

    return provider, api_key


def _color_for_line(line: str) -> str:
    """Pick a color for a log line based on keyword matching."""
    l_upper = line.upper()
    if "ERROR" in l_upper:
        return "#ef4444"
    if any(w in l_upper for w in ["SKIP", "WARN", "STALE"]):
        return "#facc15"
    if any(w in l_upper for w in ["FRESH", "COMPLETE", "READY", "OK"]):
        return "#6ee7b7"
    return "#93c5fd"


def render_log_html(lines: list[str], max_height: int = 200) -> str:
    """Build styled HTML for a list of log lines. Returns raw HTML string."""
    log_html = "".join([
        f"<div style='color:{_color_for_line(l)};font-size:12px;font-family:monospace;padding:1px 0'>{l}</div>"
        for l in lines
    ])
    return (
        f"<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;"
        f"padding:12px;max-height:{max_height}px;overflow-y:auto'>{log_html}</div>"
    )
