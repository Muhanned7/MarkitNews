"""
Database migration for QPM (Quantitative Portfolio Manager)
Creates portfolios, positions, transactions, and analysis_snapshots tables.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:123@localhost:5432/MarketPulse")

MIGRATION_SQL = """
-- 1. Portfolios table
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    base_ccy VARCHAR(10) DEFAULT 'USD',
    benchmark VARCHAR(10) DEFAULT 'SPY',
    cash NUMERIC(15, 2) DEFAULT 100000.00,
    target_vol NUMERIC(6, 4) DEFAULT 0.1500,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON portfolios(user_id);

-- 2. Positions table
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    quantity NUMERIC(15, 4) NOT NULL,
    avg_cost NUMERIC(15, 4) NOT NULL,
    side VARCHAR(10) DEFAULT 'long',
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_portfolio_ticker UNIQUE(portfolio_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_positions_portfolio ON positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);

-- 3. Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    qty NUMERIC(15, 4) NOT NULL,
    price NUMERIC(15, 4) NOT NULL,
    fees NUMERIC(10, 2) DEFAULT 0.00,
    note TEXT,
    thesis TEXT,
    sizing_method VARCHAR(50),
    invalidation_price NUMERIC(15, 4),
    snapshot_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_transactions_portfolio ON transactions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_transactions_ticker ON transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_transactions_ts ON transactions(ts DESC);

-- 4. Analysis snapshots table
CREATE TABLE IF NOT EXISTS analysis_snapshots (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    price_at_ts NUMERIC(15, 4) NOT NULL,
    recommendation VARCHAR(20) NOT NULL,
    conviction INTEGER NOT NULL,
    target NUMERIC(15, 4),
    expected_return NUMERIC(10, 2),
    horizon_days INTEGER DEFAULT 63,
    invalidation_price NUMERIC(15, 4),
    scenarios_json JSONB,
    metrics_json JSONB,
    agent_outputs_json JSONB,
    model VARCHAR(100) DEFAULT 'mistral-small-latest',
    prompt_hash VARCHAR(64),
    mock_mode BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ticker ON analysis_snapshots(ticker);
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_ts ON analysis_snapshots(ticker, ts DESC);
"""

def run_migration():
    print(f"Connecting to database {DB_URL} ...")
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        print("Executing QPM database migrations ...")
        cursor.execute(MIGRATION_SQL)
        print("QPM tables created successfully!")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_migration()
