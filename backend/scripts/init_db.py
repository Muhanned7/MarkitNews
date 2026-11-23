"""
One-shot, idempotent database setup for a fresh deployment.
Render runs this as the backend's preDeployCommand before every deploy.

Order:
  1. schema.sql            -> core tables (users, watchlist, tickers, articles, ...)
  2. migrate_qpm SQL       -> portfolios, positions, transactions, analysis_snapshots
  3. realized_pnl column   -> read by portfolio_router.py but never created by the migration
  4. RISK_SCHEMA_SQL       -> risk_limits, risk_limit_audit, limit_breaches, limit_overrides

Everything uses IF NOT EXISTS, so re-running on every deploy is safe.
Never prints DATABASE_URL (it contains the password).

Run from backend/:  python scripts/init_db.py
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.join(BACKEND_DIR, "scripts"))

load_dotenv()

from migrate_qpm import MIGRATION_SQL  # noqa: E402
from agents.risk_limits import RISK_SCHEMA_SQL  # noqa: E402

REALIZED_PNL_SQL = (
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS realized_pnl NUMERIC(15, 4) DEFAULT 0;"
)


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("init_db: DATABASE_URL is not set")

    with open(os.path.join(BACKEND_DIR, "schema.sql"), encoding="utf-8") as f:
        schema_sql = f.read()

    steps = [
        ("core schema (schema.sql)", schema_sql),
        ("QPM tables", MIGRATION_SQL),
        ("transactions.realized_pnl", REALIZED_PNL_SQL),
        ("risk-limit tables", RISK_SCHEMA_SQL),
    ]

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for label, sql in steps:
                cur.execute(sql)
                print(f"init_db: {label} ready")
    finally:
        conn.close()
    print("init_db: done")


if __name__ == "__main__":
    main()
