# PSX T+1 Scanner — Project Summary

## The Starting Point

You're a PSX trader focused on **Shariah compliant stocks** who does T+1 trades (buy today, sell tomorrow) and short swings (3-5 days). You've been paying for signal groups on WhatsApp that send daily buy/sell calls with entry, target, and stoploss. Your question was simple: **"What are those groups doing that we can't automate?"**

---

## Phase 1: Expert Roundtable (3 Agents)

We created three expert agents to brainstorm ideas:

- **Rashid Malik** — Senior Stock Broker, 25 yrs at Arif Habib Ltd
- **Farah Siddiqui** — Financial Advisor, 25 yrs specializing in PSX
- **Kamran Sheikh** — Professional Day/Swing Trader, 25 yrs on PSX

### The 5 App Ideas Generated

| # | Idea | What It Does |
|---|------|-------------|
| 1 | PSX Momentum Scanner | Real-time volume spikes, breakout detection, broker-wise flow tracking |
| 2 | Sector Rotation Radar | Policy-driven sector tracking, SBP rate decisions, heatmaps |
| 3 | Smart Entry/Exit Planner | Auto-generates trade plans with entry, target, stoploss, position sizing in PKR |
| 4 | PSX Insider & Filing Tracker | Director trades, earnings surprises, corporate action calendar |
| 5 | PSX Pattern & Confluence Screener | Multi-indicator screener (RSI + EMA + MACD + volume + patterns) |

### Expert Consensus

The panel agreed your need was a combination of **Ideas 1 + 3 + 5** — a single app that scans the market, applies multiple technical signals (confluence), and generates structured trade plans with exact price levels.

---

## Phase 2: Defining Your Requirements

Through discussion, we narrowed down exactly what you need:

- **Core output:** Top 10 picks (not 5) with buy range, target 1, target 2, stoploss, risk:reward
- **Stock universe:** KMI-30 or KMI-100 (top 100 from KMI All Shares — all Shariah compliant)
- **Approach:** Option C — Hybrid (technical rules + AI market context)
- **Features:** Top 10 picks + Sector heatmap (heatmap deferred to Phase 2)
- **Added later:** Share picks modal for copy-paste to WhatsApp

---

## Phase 3: Key Technical Decisions

### Data Source Discussion

We explored where to get PSX stock data:

| Source | Status | Cost |
|--------|--------|------|
| PSX Data Portal (dps.psx.com.pk) | Has internal API endpoints but CORS-blocked from browser | Free but inaccessible |
| Sarmaaya.pk | Client-side rendered, no fetchable data | Free but inaccessible |
| Capital Stake API | Official PSX vendor | Paid |
| TradingView Data API | Has PSX data | $10-80/month |
| psx-data-reader (Python) | Open source scraper | Free but Python-only |
| AI web search | Can read publicly available PSX data | Free (included in Claude plan) |

**Result:** Direct API fetch (Option 2) failed — all endpoints CORS-blocked. We went with AI web search as the data source.

### AI Provider Discussion

| Provider | Free Tier | Notes |
|----------|-----------|-------|
| Claude (built-in) | Included in Claude plan | Default, no API key needed |
| Google Gemini | 250 req/day free | Best free alternative |
| Groq | Free developer tier | Ultra-fast, good for speed |
| OpenRouter | 20 RPM free | One key, many models |
| DeepSeek | Generous credits | Cheapest paid option |

**Result:** App built with provider-agnostic settings panel. Claude built-in works out of the box. User can switch to any provider by entering API key.

### Index Correction

During testing, we discovered **KMI-100 doesn't exist** as an official PSX index. The actual Shariah indices are:
- **KMI-30** — Top 30 most liquid Shariah compliant stocks
- **KMI All Shares** — ~280 Shariah compliant stocks

We created a "KMI-100" option that represents the top 100 stocks from KMI All Shares by market cap.

---

## Phase 4: Architecture Evolution

### v1 — Single AI Call (Initial Build)
Everything in one shot: AI searches web, finds stocks, analyzes, picks top 10.

**Problems found:**
- AI hallucinated prices (made up numbers when it couldn't find real data)
- Included non-Shariah stocks (BAFL appeared in results)
- No way to verify data quality
- Wrong prices led to wrong entry/target/stoploss levels

### v2 — Hardcoded Lists + AI Analysis
Added hardcoded KMI-30 and KMI All Shares ticker lists. AI could only pick from allowed list.

**Problems found:**
- Hardcoded lists go stale when PSX recomposes indices (every 6 months)
- Still relied on AI for price data (hallucination risk)
- Unnecessary complexity with client-side Shariah validation

### v3 — Two-Step AI (Final Architecture)

```
STEP 1: DATA COLLECTOR (AI + web search)
  → Searches PSX data sources on the web
  → Returns ONLY raw data: ticker, price, volume, change%
  → No analysis, no opinions, no picks
  → Output: JSON array of 30-50+ stocks with verified numbers

STEP 2: ANALYST (AI, NO web search)
  → Receives Step 1 data as input context
  → Can ONLY pick from stocks in the provided dataset
  → Cannot hallucinate prices (uses exact numbers from Step 1)
  → Applies technical rules and risk profile
  → Output: Top 10 ranked picks with entry/target/stoploss
```

**Why this is better:**
- Separation of concerns: data fetch vs analysis
- Step 2 AI has NO web search — can't make up data
- Prices in picks match real market data
- If Step 1 can't find a stock's price, it simply isn't included

---

## Phase 5: UI/UX Design & Iterations

### Design Concept Selection

We presented 3 pre-scan interaction concepts:
- **Concept A:** Pre-scan filters (risk, sectors, trade style)
- **Concept B:** Live scan terminal (watch AI work in real time)
- **Concept C:** Both combined ← **Selected**

### Final UI Flow

```
1. SETTINGS — AI provider, data source, API key
2. FILTERS — Index (KMI-30/100), risk, trade style, sector focus
3. MOCK/LIVE TOGGLE — Test UI without burning API tokens
4. SCAN BUTTON — "Scan KMI-100 now"
5. LIVE TERMINAL — Watch step-by-step progress
6. MARKET SUMMARY — Bearish/Bullish banner with index direction
7. TOP 10 CARDS — Expandable cards with all trade details
8. SHARE PICKS — Modal with copyable text format
```

### UI Issues Found & Fixed

| Issue | Fix |
|-------|-----|
| Pill buttons had no visual active state | Solid blue background (#0C447C) when selected |
| Scan button invisible | Solid blue with white text |
| Labels too faint (11px tertiary) | Bumped to 12px with font-weight 500 |
| Signal tags rendered as plain text | Hardcoded hex colors instead of CSS variables |
| New Scan button unstyled | Added gray background with visible border |
| No current price on cards | Added "Rs 440.3" next to ticker |
| No scan timestamp | Added "Scanned: 06-Apr-2026, 7:21 PM" |
| JSON parsing failures | Built robust bracket-depth JSON extractor |
| Double-click firing two API calls | Added scanRef guard |
| max_tokens too low (4000) | Increased to 8000 for 10 detailed picks |

---

## What Was Built (Final Product)

### PSX T+1 Scanner — Feature List

**Settings Panel:**
- AI provider selector (Claude/Gemini/Groq/OpenAI/DeepSeek)
- Data source selector (Web search / TradingView API)
- API key field (hidden when using Claude built-in)
- Collapsible

**Scan Filters:**
- Index universe: KMI-30 (30 stocks) or KMI-100 (top 100 Shariah compliant)
- Risk appetite: Conservative / Moderate / Aggressive
- Trade style: T+1 / Swing 3-5d
- Sector focus: 13 sectors, multi-select, with "Clear all"

**Mock/Live Toggle:**
- Mock mode: sample data, no API calls, for UI testing
- Live mode: two-step AI scan with real web data
- Visual banner showing current mode

**Live Terminal:**
- Monospace log showing each scan step with timestamps
- Color-coded: blue for info, amber for processing, green for success, red for errors
- Blinking cursor animation while scanning

**Results:**
- Market direction banner (green/red/amber background)
- "X stocks scanned" counter showing data coverage
- Top 10 expandable stock cards with:
  - Rank badge (green for top 3)
  - Ticker + current price + company + sector
  - Confidence score as colored badge
  - Buy range / Target 1 / Target 2 / Stoploss grid
  - Signal tags as colored pills
  - Risk:reward ratio
  - Reasoning text + hold period badge

**Share Picks:**
- Modal overlay with formatted text
- Copy-paste ready format for WhatsApp
- "Copy to clipboard" button with confirmation

**Disclaimer:**
- Clear "not financial advice" notice
- Mentions two-step process for transparency

---

## What's Next (Future Phases)

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 2 | Sector heatmap (which sectors are hot/cold) | Planned |
| Phase 2 | Trade journal (track wins/losses) | Planned |
| Future | Direct data feed (Capital Stake API or TradingView) | Needs paid subscription |
| Future | Backend server for reliable data fetching (no CORS) | Needs hosting |
| Future | Insider/corporate action alerts | Planned |
| Future | Historical backtest of scanner accuracy | Planned |

---

## Key Lessons Learned

1. **PSX data access is hard** — No free, reliable API exists for PSX data. Everything is either CORS-blocked, client-side rendered, or behind paid licenses.

2. **AI should not be your database** — Using AI to fetch AND analyze data leads to hallucinated prices. Separating data collection from analysis significantly improves accuracy.

3. **KMI-100 doesn't exist** — Important to understand the actual PSX index structure (KMI-30 and KMI All Shares) before building.

4. **Shariah compliance must be enforced at the data level** — Telling the AI "only pick Shariah stocks" doesn't work. The data source itself must be filtered to only include KMI All Shares constituents.

5. **Mock mode saves tokens** — Adding a mock data toggle early in development saves significant API costs during UI iteration.

6. **CSS variables don't always render in artifacts** — Hardcoded hex colors are more reliable for critical UI elements like signal tags and confidence badges.
