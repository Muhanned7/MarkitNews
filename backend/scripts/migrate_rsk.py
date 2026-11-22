"""
RSK-002/003 migration: risk_limits, risk_limit_audit, limit_breaches, limit_overrides.
Idempotent (CREATE ... IF NOT EXISTS). The API also creates these lazily on first use.
Run from backend/:  python scripts/migrate_rsk.py
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.risk_limits import RISK_SCHEMA_SQL  # noqa: E402

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:123@localhost:5432/MarketPulse")

if __name__ == "__main__":
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(RISK_SCHEMA_SQL)
        print("RSK tables ready: risk_limits, risk_limit_audit, limit_breaches, limit_overrides")
    finally:
        conn.close()
