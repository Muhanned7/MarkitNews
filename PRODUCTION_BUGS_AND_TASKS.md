# Production Bugs & Remediation Task Plan

> **Source:** Live QA & Security Audit (Chrome + unauthenticated API probing across all 7 pages)
> **Notebook Log:** [`PRODUCTION_BUGS_NOTEBOOK.ipynb`](PRODUCTION_BUGS_NOTEBOOK.ipynb)

---

## Priority Overview

| Priority | Category | Tasks |
| :--- | :--- | :--- |
| **P0 (Critical)** | Auth, IDOR, Fabricated News/Contradictions, Fake Home Feed | `PROD-001` – `PROD-004` |
| **P1 (High)** | Price Consistency, Breach Counts, Analysis & Portfolio UI Math Gaps | `PROD-005` – `PROD-008` |
| **P2 (Medium)** | Performance, API Deduplication, Paywall Enforcement, Sidebar Links, Quant Demo Labels | `PROD-009` – `PROD-012` |
| **P3 (Security)** | HTTP Security Headers, `httpOnly` Cookie Auth, Strict Search Input Validation | `PROD-013` – `PROD-015` |

---

## 🔴 P0 — Critical Security & Credibility Bugs

### `PROD-001` — Enforce Authentication & Portfolio Ownership (IDOR) on Portfolio and Risk Endpoints
- **Bug:** Unauthenticated requests return full portfolio holdings, transactions, risk metrics, limits, and breach summaries:
  - `GET /api/portfolios` and `GET /api/portfolios/1`
  - `GET /api/portfolios/1/risk` and `GET /api/portfolios/1/limits`
  - `GET /api/risk/breaches/summary`
  - Plus sibling portfolio/risk sub-routes lack ownership checks (`portfolio.user_id == current_user.sub`), allowing IDOR across users.
- **Fix:**
  - Require JWT auth (`Depends(get_current_user)` or cookie/header auth) on all `/portfolios*` and `/risk*` FastAPI routes and Next.js proxy routes.
  - Enforce ownership checks (`user_id = int(user["sub"])`) on every portfolio query and mutation, returning `403`/`404` for unauthorized IDs.
- **Status:** Completed ✅

### `PROD-002` — Remove Fabricated News Fallback in `/api/search`
- **Bug:** Searching gibberish (`"zzqqxx"`) or real tickers returns fabricated template articles (`"ZZQQXX Posts Resilient Quarterly Operational Metrics…"`) falsely attributed to Reuters, Bloomberg, and FT.
- **Fix:**
  - Remove fabricated/template article generation in `app/api/search/route.js`.
  - Return real NewsAPI / live feed results or an empty list `[]` with an honest status when no live articles match (or NewsAPI is unconfigured).
- **Status:** Completed ✅

### `PROD-003` — Replace Hardcoded Placeholder Home News Feed & Ticker Strip with Live Data
- **Bug:** Home news feed shows static placeholder headlines (`"Fed Holds Rate Steady… 15m ago"`) linking to generic section pages (`reuters.com/markets`) and hardcoded ticker percentages, contradicting the Free plan's `"Real-Time Market News Feed"`.
- **Fix:**
  - Wire the home page news feed and market ticker strip to live backend/API data (e.g., `/api/tickers` and `/api/search` or live RSS/yfinance endpoint) with real article URLs and timestamps, plus an honest empty/loading fallback when offline.
- **Status:** Completed ✅

### `PROD-004` — Sanitize Contradiction Radar Demo Data (Fictional Company & Outlets)
- **Bug:** `lib/mockContradictions.js` describes a fabricated explosion at a real company (`PT Tsingshan`) with made-up quotes credited to real outlets (`Bloomberg`, `FT`, `Antara`) and ends with `"Strong risk-reward buy opportunity"`.
- **Fix:**
  - Replace real company/outlet names in the illustrative demo scenarios with clearly fictional entities (e.g., `Meridian Alloy Corp`, `GlobalWire Daily`, `Archipelago Press`) and neutral analytical language (no fabricated buy recommendations), while keeping live Contradiction Radar wired to real verified feeds.
- **Status:** Completed ✅

---

## 🟠 P1 — Wrong or Inconsistent Numbers & Analysis/Portfolio UI Gaps

### `PROD-005` — Unify Live Ticker Pricing Across Analysis, Portfolio, and Position Sizing
- **Bug:** `AAPL` displays `$355.58` on the analysis page, `$228.50` in the portfolio, and `~$232` in position sizing (`$12,082 / 52 shares`).
- **Fix:**
  - Ensure Portfolio holdings, Position Sizing, and Analysis all read from one shared live price source (yfinance / shared backend market-price helper) instead of mixing stale DB seed prices or synthetic mock prices.
- **Status:** Completed ✅

### `PROD-006` — Reconcile Hard-Breach Count Between Header and Limits Tab
- **Bug:** Header displays `"6 Hard Breaches"` while the Limits tab displays `"4 hard"`.
- **Fix:**
  - Unify the breach aggregation query/filter between `/api/risk/breaches/summary` and `/api/portfolios/:id/limits` so both count active/unacknowledged hard breaches identically (and scope to the user's active portfolio).
- **Status:** Completed ✅

### `PROD-007` — Fix Analysis Page Data & Rendering Gaps
- **Bug:** Multiple rendering and consistency issues on `app/analysis/[ticker]/page.jsx` and backend synthesis/agents:
  1. `"Expected return null% (63d)"` when `expected_return` is null.
  2. `"Target Daily Risk Budget: % / day"` with missing value.
  3. `"Half-Kelly 81.31%"` shown even when `expected_return` is null (should be hidden).
  4. Conviction-scaled sizing shows `"conviction 8/10"` while recommendation says `5/10`.
  5. Risk card says `FAIL` while summary says `Risk: Medium` and `Risk/reward: Favorable` on a `HOLD` with `2.8%` downside.
  6. `"Grade C (0.92)"` reads oddly (numeric score not aligned with capped grade).
  7. Technical card says `"above"` without stating above what (e.g., `"Above 50-day & 200-day SMA"`).
  8. Boilerplate investment thesis (`"Enterprise cloud adoption"` / `"vertical component integration"` for Apple).
- **Fix:**
  - Guard null `expected_return` and hide Half-Kelly when unavailable; populate Target Daily Risk Budget; pass live recommendation conviction into sizing; align Risk/Reward & Grade display when Risk agent fails; clarify Technical SMA labels; remove generic hardcoded fallback thesis bullets.
- **Status:** Completed ✅

### `PROD-008` — Fix Portfolio Header Return Percentage Context & Pluralization
- **Bug:** `"+$2,876.75 (5.97%)"` sits under Total NAV (`$151k`), where `5.97%` is return on invested equity (`$48k`), not Total NAV (`~1.9%`). Also `"Across 1 sectors"` should be `"1 sector"`.
- **Fix:**
  - Clarify return basis (show return on invested capital explicitly or compute return on Total NAV consistently) and fix singular/plural `"sector"` vs `"sectors"`.
- **Status:** Completed ✅

---

## 🟡 P2 — Performance, UX & Monetization Enforcement

### `PROD-009` — Improve AI Analysis Latency UX (Cached Report / Progressive Status)
- **Bug:** AI analysis takes 70–90s showing only a static skeleton screen.
- **Fix:**
  - Show cached latest snapshot immediately when available (with a "Refreshing live analysis…" banner) and display progressive step-by-step agent status updates instead of a blank skeleton.
- **Status:** Completed ✅

### `PROD-010` — Deduplicate Repeated API Calls Across Pages & Components
- **Bug:** `/api/portfolios/*` fires up to 5× during navigation; watchlist, search, and wallet each fire 2× per page load.
- **Fix:**
  - Fix unstable `useEffect` dependencies, share fetched state via context/in-flight request cache, and remove redundant fetches across `Navbar`, `Sidebar`, `AuthContext`, and page components.
- **Status:** Completed ✅

### `PROD-011` — Enforce Pro Package Paywall on Backend `/analyse/{ticker}`
- **Bug:** A Starter Free plan account can run the full 6-agent analysis advertised as Pro.
- **Fix:**
  - Add a backend subscription/plan check in `POST/GET /analyse/{ticker}` returning `402 Payment Required` (or `403` with `upgrade_required: true`) for Starter Free users, and handle it cleanly in the frontend with the Upgrade Modal.
- **Status:** Completed ✅

### `PROD-012` — Convert Sidebar Navigation Buttons to Semantic `<Link>` Elements & Fix Quant Demo Labels/Grid
- **Bug:**
  1. Sidebar items are `<button>` elements rather than `<Link href="...">`, breaking middle-click/new-tab, bookmarking, and screen-reader semantics.
  2. Quant Research uses synthetic `mock100` data (`t-stat 98`, `IC IR 7.4`) without a clear `"Synthetic Demo Data"` banner, and the 6th tear-sheet stat card wraps onto an orphan row.
- **Fix:**
  - Convert Sidebar navigation items to Next.js `<Link>` elements.
  - Add a prominent `"Synthetic Demo Data (mock100)"` badge/banner on Quant Research and adjust the tear-sheet stat grid (e.g., 3×2 or 6-col responsive grid) so the 6th card never orphans.
- **Status:** Completed ✅

---

## 🔵 P3 — Security Hardening

### `PROD-013` — Add Security Headers & Disable `X-Powered-By` in `next.config.mjs`
- **Bug:** Missing `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and `X-Powered-By: Next.js` is exposed.
- **Fix:**
  - Set `poweredByHeader: false` and add a `headers()` configuration in `next.config.mjs`.
- **Status:** Completed ✅

### `PROD-014` — Migrate Auth Token from `localStorage` to `httpOnly` Cookie
- **Bug:** JWT token and plaintext user email are stored in `localStorage`, exposing them to XSS.
- **Fix:**
  - Set an `httpOnly`, `SameSite=Lax` (and `Secure` in prod) cookie in `/api/auth/login` and `/api/auth/register`, add `/api/auth/me` and `/api/auth/logout`, forward the cookie as `Authorization: Bearer` in Next.js API routes, and remove JWT/email storage from `localStorage`.
- **Status:** Completed ✅

### `PROD-015` — Validate Input Strictly on `/api/search` (Return `400` on Malformed JSON)
- **Bug:** Sending malformed JSON to `/api/search` returns `200` with results instead of `400 Bad Request`.
- **Fix:**
  - Explicitly catch JSON parse errors and invalid/missing query bodies in `app/api/search/route.js` and return `400 Bad Request` with a clear error message.
- **Status:** Completed ✅
