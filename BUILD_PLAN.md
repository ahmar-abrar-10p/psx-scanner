# PSX Scanner — Build Plan

_Captured 2026-04-08. This is the working plan for rebuilding the scanner from the current MVP into a serious, self-improving tool. Each build is a checkpoint — stop, verify, use it, then move on._

---

## Guiding principles

1. **We are not predicting direction.** We are detecting setups with asymmetric payoff and letting risk management do the rest. A 45% win rate with 2:1 R:R is the real target.
2. **Python computes, AI judges.** All price math, levels, swing points, Renko, P&F, Magic Lines happen deterministically in Python. LLM agents never touch OHLCV numbers — they reason about pre-computed features and produce judgment calls.
3. **React to structure, don't forecast.** Detect breakouts, breakdowns, pullbacks, trend state changes — the same things human chartists look for — across 100 stocks in seconds.
4. **Every change is measurable.** Nothing ships without a way to tell if it improved outcomes. The trade log is not optional.
5. **Human in the loop on learning.** The retrospective agent proposes; the human approves. No auto-rule-updates.

---

## Final agent architecture

### Main scan pipeline (5 sequential agents) — every agent sees all 100 stocks

No pre-filtering. Every agent receives the full 100-stock universe so the AI has complete visibility and can spot edge cases that hardcoded rules would miss.

| # | Agent | Input | Output | Why it exists |
|---|---|---|---|---|
| 1 | **Market Regime Analyst** | KSE-100 technicals, breadth, sector rotation | JSON regime state | The single biggest filter. Downstream agents behave differently based on regime. |
| 2 | **Technical Analyst** | **All 100 stocks** (full feature set) + regime | Ranked list of all 100 with conviction score, setup type, narrative for top performers | The real screening brain. Sees everything, reasons about combinations. |
| 3 | **News & Event Screener** | **All 100 stocks** + ranking from Agent 2 + scraped headlines + PSX announcements | Per-stock news flags, stocks to avoid, tailwinds | Human chartists always check news. We don't filter to 20 first — every stock gets news-checked so a low-ranked stock with a major positive catalyst can still surface. |
| 4 | **Risk Screener** | **All 100 stocks** with Agent 2 + 3 context | Per-stock risk assessment, position-size recommendations, macro warnings | Applies hard filters (events, macro warnings). Computes sizing AFTER Strategist picks the stop. |
| 5 | **Trade Strategist** | All 100 with all accumulated context | Top 10 with exact entry / chart-based stoploss / target / R:R | The only agent that outputs executable trade plans. Picks stoploss from chart structure. |

**Note on Agent 4 (Risk Screener) ordering with Agent 5 (Strategist):** Risk sizing depends on stoploss distance, but stoploss is picked by the Strategist from chart structure. So Agent 4's first pass produces risk warnings and rules; the Strategist applies them and picks final stops; sizing math is computed in `risk_screener.py` as a post-processing step on the Strategist's output, not as a separate LLM call. Effectively Agent 4 is a "rules + final math" stage, not just a sequential LLM agent.

### Retrospective pipeline (1 agent, runs weekly)

| # | Agent | Input | Output |
|---|---|---|---|
| 6 | **Retrospective Analyst** | `trades.sqlite` — all closed trades with features + outcomes | Markdown report: what worked, what didn't, proposed rule tweaks (for human review only) |

---

## Data layer — what Python computes

### Standard technicals (most already exist, some to add)
- RSI(14), EMA(20), EMA(50), **EMA(200)**, MACD(12,26,9), ATR(14)
- **ADX** (trend strength), **Bollinger Band width** (volatility compression)
- Volume ratio vs 20-day average, gap-up/gap-down flags

### Structural features (the big addition)
- **Swing highs and lows** — pivot points over last 60 bars
- **Horizontal levels** — clustered from swings
- **Magic Lines** — nearest untested swing-high resistance above current price (default rule: 2+ touches in last 60 days, to be refined when user provides mentor's exact definition)
- **Breakout detection** — closed above a known level today, on above-average volume
- **Breakdown detection** — closed below a known support today
- **Pullback detection** — in uptrend, price touching EMA20/50 and turning up
- **Higher-highs / higher-lows count**
- **Distance to Magic Line (%)** — how close we are to the next breakout trigger

### Aggregation charts (filter use, not drawn)
- **Renko state** — last 3 brick directions, count since last reversal
- **P&F** — current column (X/O), most recent signal, bullish percent

### Market regime features
- KSE-100 trend state (up/down/range) via EMA slopes
- Our own breadth index (% of 100 stocks above EMA20, above EMA50)
- Sector rotation — rank sectors by average 5-day return

---

## Stoploss and position sizing — clarified

**Stoploss is a chart-structure decision, not a risk-tolerance decision.**

- The **Trade Strategist** picks the stoploss based on chart structure: nearest swing low, breakout retest level, Magic Line, or support level — whichever is closest and most defensible
- A Python sanity check ensures the stop is at least 1× ATR14 away (so normal noise doesn't trigger it)
- Stoploss reason is captured and shown to the user (e.g., `"below swing low at 268"`, `"below Magic Line at 265"`)

**Position sizing is the math that follows from a stoploss:**

```
shares_per_100k_portfolio = (100,000 × 0.01) / (entry_price − stoploss_price)
```

- Default risk per trade: **1%** (stateless — user scales to their own portfolio mentally)
- Wide stoploss → fewer shares; tight stoploss → more shares; **PKR risk stays constant**
- Risk Screener computes this after the Strategist picks the stop
- Later phase (Build 7+): optional portfolio-size input in sidebar for absolute share counts

## LLM provider strategy — multi-provider with Ollama Cloud added

The current code already supports Gemini, Groq, and OpenAI as a dropdown. We extend this to include **Ollama Cloud** so the user can switch providers without code changes.

| Provider | Role | Why |
|---|---|---|
| **Gemini 2.0 Flash** | Default for production scans | Free tier covers 1M tokens/day, fast (~5-8s/call), already wired, strong JSON output |
| **Groq** | Backup, fast iterations | Very fast inference but per-minute token limits can bite on large prompts |
| **OpenAI GPT-4o-mini** | Backup | Reliable but paid |
| **Ollama Cloud** (new) | Experimental + non-critical agents + dev iteration | Flat-rate billing (no token anxiety), strong open-weight models like `gpt-oss:120b-cloud`, first-party web search API for News Agent |

**Strategy:**
- **Build 2:** Gemini stays primary. Ollama added as a selectable provider (one extra entry in the dropdown). Both work side by side.
- **Build 5 (Retrospective):** test Ollama here first because it's batch / non-critical. If quality holds up, migrate other agents.
- **Build 6 (News Agent):** consider Ollama's web search API as a built-in alternative to manual scrapers
- **Long-term:** stay multi-provider. Never lock in.

**What we're NOT doing:**
- Not switching everything to Ollama right now — Gemini is working
- Not running Ollama locally on the user's machine — cloud is the path that solves the token concern without hardware requirements

## Storage

- **OHLCV + computed technicals cache:** parquet files at `cache/technicals_YYYY-MM-DD.parquet` (already in place, extend as features grow)
- **Trade log:** `trades.sqlite` (SQLite, zero-install, stdlib)
  - `trades` table — every pick the Strategist outputs, with full feature vector at entry time
  - `outcomes` table — filled in by daily tracker: exit reason, exit price, P&L, bars held
  - Schema designed for historical backfill so we can replay the scanner on past data once it's built
- **News cache:** short-lived (1-day) cache of scraped headlines to avoid re-scraping on every scan

---

## Build phases

Each phase is a checkpoint. Run, verify, use it for a few days, then advance.

### ✅ Build 0 — Current MVP (already done)
- Streamlit UI, yfinance data, pandas-ta indicators
- Two simple agents (Analyst + Strategist) producing top-10 picks
- Cache layer with force-refresh
- Rate limit fix (yfinance 1.2.1 + chrome impersonation)
- **Status:** working baseline. This is what "good enough to use today" looks like.

---

### Build 1 — Richer data layer (the foundation for everything else)

**Goal:** replace the current thin feature set with the full rich one. No agent changes yet.

**Tasks:**
1. Read current `KMI_top100.csv` structure
2. Web search for PSX sector of each of the 100 symbols, add `sector` column (user will vet)
3. Verify KSE-100 index ticker on yfinance (`^KSE`, `KSE.KA`, or fallback)
4. Bump `LOOKBACK_DAYS` from `"60d"` to `"1y"` in `data.py`
5. Add `features.py` — new module for all feature computation, split out of `data.py`:
   - Swing point detection
   - Horizontal level clustering
   - Magic Line computation
   - Breakout/breakdown detection
   - Pullback detection
   - Renko bricks
   - P&F signals
   - ADX, BB width, EMA200
6. Add `regime.py` — computes market-level features (index trend, breadth, sector rotation)
7. Update cache format to include all new features
8. **No UI or agent changes yet.** Cache should still load instantly.

**Deliverable:** scanner runs, cache file is bigger, new features visible in stock dicts but no agents use them yet.

**Test before advancing:** run the existing 2-agent pipeline with the new feature set — picks should still be produced, likely unchanged.

---

### Build 2 — Main pipeline agents (the big rewrite)

**Goal:** replace the 2-agent pipeline with the 5-agent pipeline. News stubbed. Add Ollama Cloud as a provider option.

**Tasks:**
1. Define JSON output schemas for Agents 1-4 (Pydantic models for validation)
2. **Agent 1 — Market Regime Analyst**: new file `agents/regime_analyst.py`. Takes regime features from `regime.py`, outputs structured JSON.
3. **Agent 2 — Technical Analyst**: new file `agents/technical_analyst.py`. Takes all 100 stocks + regime JSON, outputs **ranked list of all 100** with setup type and confluence (no pre-filter).
4. **Agent 3 — News & Event Screener**: new file `agents/news_screener.py`. **Initially stubbed** — returns empty news, empty events. Real news/events come in Build 4. Agent processes all 100 stocks (pass-through for now).
5. **Agent 4 — Risk Screener**: new file `agents/risk_screener.py`. Applies regime-aware rules across all 100, computes 1%-risk position sizing math after Strategist picks the stop.
6. **Agent 5 — Trade Strategist**: refactored from current `agents.py`. Takes all 100 with all context, picks chart-based stoploss, outputs top 10 trade plans.
7. **Add Ollama Cloud provider** in `agents.get_llm()` and `get_crewai_llm()` factory functions. Add to UI dropdown. Test that all 5 agents can run on either Gemini or Ollama by switching the dropdown.
8. `scanner.py` orchestrates the 5-agent sequential pipeline with JSON validation between steps
9. Each agent has retry-on-invalid-JSON logic (max 2 retries)
10. Per-agent progress updates in Streamlit log

**Deliverable:** working 5-agent pipeline producing picks, switchable between Gemini and Ollama Cloud. News agent is a pass-through (returns empty news).

**Test before advancing:** run the scan, verify picks still look reasonable, and Agent 1-4 outputs are valid JSON.

---

### Build 3 — Trade logging + outcome tracker (the measurement layer)

**Goal:** start measuring. Nothing advances without this.

**Tasks:**
1. `trade_log.py` — SQLite helper module with:
   - `init_db()` — creates schema if not exists
   - `log_pick(pick_dict, feature_snapshot)` — called by scanner after Agent 5
   - `mark_outcome(trade_id, exit_data)` — called by tracker
   - `get_closed_trades(since_date)` — for Retrospective Analyst
2. Schema design (supports backfill):
   - `trades`: id, date, symbol, entry_price, target1, target2, stoploss, rr_ratio, risk_pct, conviction_rank, setup_type, feature_vector_json, regime_snapshot_json, source (`live` / `backfill`)
   - `outcomes`: trade_id, exit_date, exit_price, exit_reason (`target1_hit`/`target2_hit`/`stoploss_hit`/`timeout`), pnl_pct, bars_to_exit, notes
3. Wire `log_pick` into `scanner.run_scan` — every pick logged automatically
4. `tracker.py` — daily outcome-checking job:
   - Fetches next-day OHLCV for all open trades
   - Checks if high >= target1, low <= stoploss, etc.
   - Marks outcomes in SQLite
   - Run on-demand button in UI + can be automated later
5. Streamlit page 2: "Trade History" — table of all picks with outcomes, win rate, avg R:R realized

**Deliverable:** every scan logs picks. Daily button updates outcomes. Trade History page shows running performance.

**Test before advancing:** run a scan, check SQLite has rows, hit "update outcomes", verify state transitions work.

---

### Build 4 — PSX announcements scraper (unblock Agent 3 partially)

**Goal:** real structured event data so Agent 3 can filter stocks with pending earnings/board meetings.

**Tasks:**
1. `announcements.py` — scraper for `dps.psx.com.pk/announcements`:
   - Fetches announcements for next 7 days
   - Parses into `(symbol, event_type, event_date, title)` tuples
   - 1-day cache to avoid hammering
2. SBP monetary policy calendar — static list for now (meetings are announced months ahead), manual update 2x/year
3. Agent 3 (News & Event Screener) consumes these structured events — filters any stock with an event in next 2 days, adds macro warnings
4. Streamlit sidebar shows "Events in next 7 days" count

**Deliverable:** Agent 3 actually filters out stocks with pending corporate events. Picks should never include a stock with earnings tomorrow.

---

### Build 5 — Retrospective Analyst (the learning loop) + Ollama trial

**Goal:** once ~30-50 closed trades exist, make the system introspect. **First production agent to run on Ollama Cloud as a quality test.**

**Tasks:**
1. `agents/retrospective.py` — reads closed trades from SQLite
2. **Default this agent to Ollama Cloud (`gpt-oss:120b-cloud`)** since it's batch / non-critical. Allow Gemini as fallback. This is the migration test: if Ollama produces good retrospective reports, we know it can handle the rest of the pipeline too.
3. Produces a markdown report answering:
   - Overall win rate, avg R:R, total P&L%
   - Win rate by setup type (breakout, pullback, trend continuation)
   - Win rate by regime (did we do better in bullish vs choppy regimes?)
   - Which signals correlate with wins vs losses?
   - Worst trades — common patterns?
   - Proposed rule tweaks (for human review)
4. Streamlit page 3: "Retrospective" — button to run, displays latest report, archives old reports
5. **Explicitly no auto-rule-updates.** Human reads report, decides what to change, edits the rules in Python.

**Deliverable:** weekly button that produces a real analysis of what's working. First useful run needs ~4-8 weeks of data.

---

### Build 6 — News headline scraper + classifier (fill in Agent 3)

**Goal:** unstructured news feeding Agent 3. Last because it's the most brittle.

**Two paths to evaluate:**

**Path A — Manual scrapers (traditional approach):**
1. `news_scraper.py` — scrapers for:
   - Business Recorder (brecorder.com)
   - Dawn Business (dawn.com/business)
   - Profit Pakistan (profit.pakistantoday.com.pk)
   - Mettis Global (mettisglobal.news)
   - Respect `robots.txt`, reasonable delays, user-agent header
2. Headline-to-ticker matching via company-name dictionary
3. LLM classifies sentiment per matched headline

**Path B — Ollama Cloud web search API:**
1. Use Ollama's first-party web search tool to query "PSX [SYMBOL] news last 24h" for stocks of interest
2. Let the cloud model search and summarize in one call
3. No scraper maintenance, no broken-site issues
4. Costs against Ollama's web search free tier (separate from inference quota)

**Decision:** prototype both. Path B is far less brittle if it works. Path A is the fallback. We pick after testing both on 10 stocks during this build.

**Common to both paths:**
- Process all 100 stocks (per the no-pre-filter rule), but only deeply investigate stocks where a headline match is found
- Cache results for 1 day to avoid re-fetching
- Output: `{symbol: {headlines: [...], sentiment_score: -1 to +1, concerns: [...]}}`

**Deliverable:** scanner avoids stocks with fresh bad news and flags stocks with tailwinds.

**Known risks (documented up front):**
- Scrapers break when sites redesign — budget ~1 fix per month
- LLM cost bumps up (20 stocks × several headlines × classification call per scan)
- Legal: always scrape responsibly

---

### Build 7+ — Optional future work (not committed)

- Intraday data if user gets paid subscription (DPS or similar)
- Portfolio size input for exact share counts
- Paper-trading mode (log picks but don't treat as real trades)
- Historical backfill runner (replay scanner on past 1-2 years of data to build trade log fast)
- Magic Line refinement once user provides mentor's exact rules
- Alternative retrospective framings: Kelly sizing from historical edge, rolling performance windows

---

## What stays the same across all builds

- Stock universe is always KMI_top100.csv (no AI-driven universe selection)
- yfinance is primary data source until a paid alternative exists
- AI never touches prices — only structured features
- Streamlit UI stays the primary interface
- `.env` stays the only place for API keys
- Mock mode stays working throughout (needed for UI dev without API calls)

---

## Open items to track

- **Magic Line rule** — user to provide mentor's exact definition when available. Default used until then.
- **KSE-100 vs KMI-30 index ticker** — to be verified against yfinance in Build 1
- **Sector mapping** — web search in Build 1, user to vet the CSV
- **Paid data source** — user open to it once system proves value. Worth revisiting after Build 5.
- **Portfolio size** — stateless for now, revisit in Build 7+
- **Ollama Cloud quality** — to be measured in Build 5 (Retrospective Agent). If `gpt-oss:120b-cloud` produces good reports, expand to other agents in Build 6+.
- **News scraping vs Ollama web search** — A/B test in Build 6, pick one or combine.
