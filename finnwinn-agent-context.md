# FinnWinn — Context for Coding Agent

You are working on **FinnWinn** (formerly named MarketPulse), a full-stack financial
news and stock analysis web application built for learning and portfolio purposes.
The owner writes the code personally and uses AI assistance to review, debug,
explain, and tutor — not to hand over complete unreviewed solutions. Keep that
spirit: prefer explaining *why*, flagging trade-offs, and making incremental,
testable changes over large unreviewed rewrites.

## Your first task, before making any changes

This document describes the *intended* architecture and known issues as of the
last working session. It is **not** a literal file-by-file, function-by-function
map of the current repo — treat it as ground truth for intent, stack, and
priorities, but **verify it against the actual code first**. Specifically:

1. Inventory the actual directory structure (frontend and backend) and produce
   a short file/function map before touching anything.
2. Confirm which of the "current state" and "known issues" items below are
   still accurate — some may already be partially fixed.
3. Flag anywhere the real code contradicts this document instead of silently
   reconciling it.

## Purpose

FinnWinn is a full-stack financial news and stock analysis app demonstrating:
a multi-agent AI pipeline, semantic search, real-time financial data
aggregation, and JWT-based authentication. Features are built and tested
incrementally — one feature implemented and verified before moving to the next.

## Stack

**Frontend**
- Next.js + React (Context API for auth state)
- CSS Modules (preferred over inline styles) + Tailwind CSS v4
- `jsonwebtoken` for JWT handling
- No direct database connection pool in Next.js — all PostgreSQL access is routed through the FastAPI backend.

**Backend**
- FastAPI (Python)
- PostgreSQL via `psycopg2` using a thread-safe `ThreadedConnectionPool` (`backend/agents/db.py`)
- Loguru for logging
- Prometheus via `prometheus-fastapi-instrumentator`, plus custom metrics in `metrics.py`

**AI / ML**
- Mistral AI (`mistral-small-latest`) — six parallel specialist agents plus one
  synthesizer agent, orchestrated with `asyncio.gather` (LangGraph was
  evaluated and deliberately not used — unnecessary at this scale)
- Pinecone (`marketpulse` index, 384 dimensions, cosine metric)
- Hugging Face `sentence-transformers/all-MiniLM-L6-v2` for embeddings

**Data sources**
- NewsAPI, Finviz (analyst ratings), yfinance (fundamentals + technical data),
  Alpha Vantage, Finnhub (ticker seeding)

**Infrastructure**
- Render.com (backend + managed PostgreSQL)
- Docker (`Dockerfile` + `.dockerignore`)

## Architecture

- **Auth flow:** FastAPI issues JWTs on login/register (`auth.py`). React Context manages
  auth state client-side. **FastAPI independently verifies JWTs on all protected endpoints**
  (`POST /analyse/{ticker}`, `GET /test/{ticker}`, `GET /watchlist`, `POST /watchlist`, `DELETE /watchlist`)
  using `user = Depends(get_current_user)`.
- **Request routing:** Frontend calls Next.js API routes (`/api/watchlist`, `/api/tickers`, `/api/search`),
  which delegate database queries to FastAPI REST endpoints, or calls FastAPI directly using a configurable
  `BACKEND_URL` (`process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'`) with `Authorization: Bearer ${token}`.
- **Agent file convention:** every agent file follows the same structure —
  `MOCK_MODE` check → increment `agent_calls` counter → `try/except` with a
  `mistral_errors` counter → `finally` block observing latency. Keep new
  agent code consistent with this pattern.
- **`MOCK_MODE`:** an environment variable that returns hardcoded agent
  responses in development, avoiding Mistral's free-tier rate limits.
- **Mistral client:** instantiated once in `agents/client.py`, with
  `load_dotenv()` called there specifically so env vars load before the
  client initializes. Do not re-instantiate the client per-request.

## Current state / completed work

- **Two-pool problem [RESOLVED]:** Consolidated database pooling into a single
  `ThreadedConnectionPool` inside `backend/agents/db.py`. Removed `pg.Pool` instantiation
  from Next.js (`lib/db.js`). All database queries (`watchlist`, `tickers`, `articles`, `searches`)
  are exposed via FastAPI backend endpoints, and Next.js routes proxy to FastAPI.
- **FastAPI-side JWT verification [RESOLVED]:** Added `user: dict = Depends(get_current_user)`
  to `POST /analyse/{ticker}`, `GET /test/{ticker}`, and all `/watchlist` routes. Updated
  frontend calls in `app/page.jsx` and `app/analysis/[ticker]/page.jsx` to pass `Authorization: Bearer ${token}`.
- **JWT malformed error [RESOLVED]:** Watchlist authentication is now handled by FastAPI's
  `HTTPBearer()` dependency and JOSE decoder, cleanly returning 401 on invalid/missing tokens without crashing.
- **Node 22 Windows build compatibility [RESOLVED]:** Handled `EISDIR` return on `readlink` for non-symlink
  files in Next.js trace plugins under Node 22 on Windows.

## Known issues to design around (next in priority)


1. **No FastAPI-side JWT verification.** Every protected FastAPI route should
   independently verify the token (e.g., via a `Depends()` dependency) rather
   than trusting that Next.js already checked it. This is defense-in-depth:
   the backend, which owns the database, should never trust "a request
   arrived" as proof of authorization.
2. **`psycopg2` is synchronous and blocks FastAPI's event loop.** FastAPI is
   an async framework, but a sync DB driver call inside an async route
   handler blocks that worker's entire event loop until the query returns —
   silently defeating the concurrency benefit of `async def` routes. Under
   load this causes latency spikes and request queueing that won't show up
   as high CPU. Fix options: migrate to an async driver (`asyncpg` or
   `psycopg3` in async mode), or wrap existing calls with
   `run_in_threadpool` as an interim measure.
3. **No confirmed per-agent timeout on the Mistral fan-out.** If one of the
   6 parallel specialist agents hangs, verify whether `asyncio.gather` hangs
   the entire request with it. Recommended: wrap each agent call with
   `asyncio.wait_for(...)` and define explicit behavior for partial failure
   (proceed with N/6 results vs. fail the request clearly).
4. **No retry/backoff on external calls** (Mistral, Pinecone, market data
   APIs). Should be bounded and applied only to idempotent/read operations —
   not blind retries on writes.
5. **Health checks likely don't verify real dependencies.** A `/health`
   endpoint should confirm actual DB reachability (and ideally key external
   dependencies), not just "process is alive."
6. **Prometheus metrics exist but alerting may not be wired up.** Confirm
   whether `mistral_errors`, DB connection saturation, and request latency
   have any alerting attached, or if metrics are collected but unmonitored.
7. **PgBouncer / connection pooler is a future step, not current.** Do not
   introduce this prematurely — only relevant once a single, async-driver
   connection pool is confirmed to still hit Postgres's connection cap under
   real load.

## Environment / config gotchas (confirm still applicable)

- `.env.local` variables use `KEY=value` syntax, no quotes.
- Postgres is configured as individual connection parameters (host, port,
  user, password, dbname), not a single connection string — this was a
  deliberate choice due to password-parsing issues with connection strings.
- ES module hoisting: any script relying on env vars at import time needs
  `import './env.js'` (or equivalent) as the **very first** import, before
  any module that reads those vars at load time.
- Pinecone SDK v7 upsert syntax is `index.upsert({ records: [{...}] })` — not
  the older array-based format. Verify SDK version before assuming this
  syntax applies.
- `psycopg2` uses `%s` placeholders, not `$1`-style.
- Turbopack previously conflicted with the `pg` package on Windows; resolved
  by pinning to Next.js 15. Verify current Next.js version before assuming
  this constraint still applies.
- Keyword matching logic needs word-boundary regex (`\b`) to avoid false
  positive substring matches (e.g., "ai" inside "raises").
- Internal vs. external Render database URLs behave differently — confirm
  which is used where before changing connection config.

## Priority order for outstanding work

If asked to help sequence or pick up work, this is the dependency-aware order
established with the project owner:

1. Two-pool consolidation (in progress)
2. FastAPI-side JWT verification
3. Fix `psycopg2` blocking the event loop
4. Per-agent timeouts on the Mistral fan-out
5. Retry/backoff on safe (idempotent) external calls
6. Health/readiness checks + alerting on existing Prometheus metrics
7. Connection pooler (PgBouncer) — only if still needed after the above
8. Horizontal scaling / multi-instance FastAPI — last, since it multiplies
   the impact of any unfixed item above

## Working style to match

- Incremental: implement one thing, get it tested/verified, then move on —
  avoid bundling multiple unrelated fixes into one change.
- Prefer CSS Modules over inline styles on the frontend.
- For notebook or code edits, don't regenerate/output whole files — describe
  exactly what changes and where (file, function, or line) unless a full
  rewrite is explicitly requested.
- Prefer short, direct answers for simple/direct questions; go deep only
  where the question calls for it.
