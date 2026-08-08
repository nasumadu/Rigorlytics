"""
db.py — single connection helper for all Rigorlytics DB scripts.

Reads the Supabase connection string from the environment. Supports either:
  DATABASE_URL   (preferred, full URI)
or the discrete pieces:
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

Supabase gives you the URI under Project Settings -> Database -> Connection string.
Use the *session pooler* / direct connection (port 5432) for migrations and
bulk ingestion; the transaction pooler (6543) is fine for the web app.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

# Match the project convention (rag.py uses python-dotenv): load .env so
# DATABASE_URL set there is visible without exporting it into the shell.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    required = ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            "No DATABASE_URL and missing " + ", ".join(missing) +
            ". Set DATABASE_URL in .env (Supabase -> Settings -> Database)."
        )
    return (
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"dbname={os.environ['PGDATABASE']} "
        f"user={os.environ['PGUSER']} "
        f"password={os.environ['PGPASSWORD']} "
        f"sslmode={os.environ.get('PGSSLMODE', 'require')}"
    )


@contextmanager
def get_conn():
    """Yield a psycopg2 connection; commit on success, rollback on error."""
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor(dict_rows: bool = False):
    """Yield a cursor inside a managed connection."""
    with get_conn() as conn:
        factory = psycopg2.extras.RealDictCursor if dict_rows else None
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
        finally:
            cur.close()


if __name__ == "__main__":
    # smoke test: print server version + row counts
    with get_cursor() as cur:
        cur.execute("select version();")
        print(cur.fetchone()[0])
        for t in ("leagues", "seasons", "teams", "players",
                  "player_seasons", "contracts", "games",
                  "game_stats", "ingestion_log"):
            try:
                cur.execute(f"select count(*) from {t};")
                print(f"  {t:16s} {cur.fetchone()[0]:>8d}")
            except Exception as e:  # table may not exist yet
                print(f"  {t:16s} (missing: {e})")
