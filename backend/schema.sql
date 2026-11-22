-- Core tables that the FastAPI code reads/writes but never creates itself.
-- (Portfolio, risk, QRA and billing tables are created automatically at runtime
--  with CREATE TABLE IF NOT EXISTS, so they are not listed here.)
--
-- DRAFT: reconstructed from the SQL in main.py / auth.py / ingestion/evaluation.py.
-- Before using in production, compare with your local DB:
--   pg_dump --schema-only -t users -t watchlist -t tickers -t articles -t searches \
--           -t agent_token_logs -t footprint_evaluations MarketPulse
-- Run once against a fresh database:  psql "$DATABASE_URL" -f schema.sql

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker     VARCHAR(16) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS tickers (
    id               SERIAL PRIMARY KEY,
    symbol           VARCHAR(16) UNIQUE NOT NULL,
    name             TEXT,
    description      TEXT,
    sector           TEXT,
    industry         TEXT,
    embedding_stored BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id         TEXT PRIMARY KEY,
    headline   TEXT,
    summary    TEXT,
    source     TEXT,
    url        TEXT,
    published  TEXT,
    score      DOUBLE PRECISION,
    sentiment  TEXT,
    confidence DOUBLE PRECISION,
    rationale  TEXT,
    sectors    TEXT[],
    query      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS searches (
    id            SERIAL PRIMARY KEY,
    query         TEXT,
    results_count INTEGER,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_token_logs (
    id                SERIAL PRIMARY KEY,
    agent_name        TEXT,
    ticker            VARCHAR(16),
    model             TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    duration_ms       DOUBLE PRECISION,
    step_number       INTEGER,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS footprint_evaluations (
    id                       SERIAL PRIMARY KEY,
    ticker                   VARCHAR(16),
    faithfulness_score       DOUBLE PRECISION,
    citation_grounding_score DOUBLE PRECISION,
    completeness_score       DOUBLE PRECISION,
    overall_quality_score    DOUBLE PRECISION,
    grade                    TEXT,
    guardrails_passed        BOOLEAN,
    hallucinations_detected  INTEGER,
    details                  JSONB,
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- agent_evaluations is also auto-created by risk_phase4.py, but without the
-- `details` column that agents/evaluator.py writes. Create it here first.
CREATE TABLE IF NOT EXISTS agent_evaluations (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(50) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    faithfulness_score NUMERIC(4, 2),
    consistency_score NUMERIC(4, 2),
    completeness_score NUMERIC(4, 2),
    overall_quality_score NUMERIC(4, 2),
    grade VARCHAR(10),
    guardrails_passed BOOLEAN DEFAULT TRUE,
    hallucinations_detected INTEGER DEFAULT 0,
    warnings JSONB,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE agent_evaluations ADD COLUMN IF NOT EXISTS details JSONB;

-- Run AFTER scripts/migrate_qpm.py: portfolio_router.py reads this column but
-- the migration never creates it.
-- ALTER TABLE transactions ADD COLUMN IF NOT EXISTS realized_pnl NUMERIC(15, 4) DEFAULT 0;
