import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
import os
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Build connection parameters from DATABASE_URL or individual parameters
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    db_user = os.environ.get("DB_USER", os.environ.get("POSTGRES_USER", "postgres"))
    db_pass = os.environ.get("DB_PASSWORD", os.environ.get("POSTGRES_PASSWORD", ""))
    db_host = os.environ.get("DB_HOST", os.environ.get("POSTGRES_HOST", "localhost"))
    db_port = os.environ.get("DB_PORT", os.environ.get("POSTGRES_PORT", "5432"))
    db_name = os.environ.get("DB_NAME", os.environ.get("POSTGRES_DB", "MarketPulse"))
    DATABASE_URL = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

# Single centralized connection pool for the entire system
pool = ThreadedConnectionPool(
    minconn=1,
    maxconn=20,
    dsn=DATABASE_URL
)

@contextmanager
def get_db_connection():
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

def query(sql: str, params=None):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description is not None:
                rows = cur.fetchall()
                conn.commit()
                return type('Result', (), {'rows': rows})()
            else:
                conn.commit()
                return type('Result', (), {'rows': []})()