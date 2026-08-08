"""
apply_schema.py — apply schema.sql through psycopg2, so no `psql` binary is
needed (installing the postgresql client on the VM requires sudo/auth).

schema.sql is plain SQL (no psql meta-commands), wrapped in a single
BEGIN/COMMIT. We run it in autocommit mode so that explicit transaction is the
one that governs — the whole file applies atomically or not at all.

Usage:
    python db/apply_schema.py
"""
from __future__ import annotations

import os

import psycopg2

from db import _dsn  # reuses the same DATABASE_URL / .env resolution

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def main() -> None:
    with open(SCHEMA_PATH, "r") as f:
        sql = f.read()

    conn = psycopg2.connect(_dsn())
    conn.autocommit = True  # let schema.sql's own BEGIN/COMMIT govern the tx
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cur.close()
        print(f"applied {SCHEMA_PATH} OK")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
