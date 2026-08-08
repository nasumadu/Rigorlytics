import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


@contextmanager
def get_conn():
    """Yield a database connection. Commits on success, rolls back on error."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, params=None):
    """Run a SELECT and return a list of dict rows."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql, params=None):
    """Run a SELECT and return a single dict row or None."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """Run an INSERT/UPDATE/DELETE. Returns affected row count."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount


def execute_many(sql, param_list):
    """Run the same statement across many parameter sets."""
    if not param_list:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, param_list)
            return cur.rowcount


def get_league_id(code):
    """Look up a league id by its code, e.g. 'NBA'."""
    row = query_one("SELECT id FROM leagues WHERE code = %s", (code,))
    return row["id"] if row else None


def log_ingestion(source, entity_type, league_id, count, status, error=None):
    """Record an ingestion run."""
    execute(
        """INSERT INTO ingestion_log
           (source, entity_type, league_id, records_processed, status, error_detail)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (source, entity_type, league_id, count, status, error),
    )
