"""
ingest_util.py — shared helpers for the ESPN ingestion scripts.

Bootstraps sys.path so `from app.players import ...` works when these scripts
are run from the project root (python db/ingest_players.py), reuses the ESPN
config already in app/players.py, and provides ingestion_log bookkeeping plus
value parsing.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager

# --- make the project's `app` package importable ----------------------------
# Append (not insert-at-0) so the script's own dir stays first on sys.path —
# otherwise `import db` would resolve to the db/ *directory* (a namespace
# package) instead of db.py, and `from db import get_conn` would fail.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)

from app.players import LEAGUES  # noqa: E402  (reuse the single source of truth)

from db import get_conn  # noqa: E402

# ESPN's data coverage floor per league (from the handoff). We don't probe the
# stats endpoint for seasons older than this — the DB may hold earlier season
# rows (e.g. pre-2002 NFL) but those get filled from other sources.
ESPN_EARLIEST = {
    "nba": 1987,
    "wnba": 1997,
    "nfl": 2002,
    "mlb": 1968,
    "nhl": 1980,
}

CURRENT_SEASON = 2025


def league_code(league_key: str) -> str:
    """players.py key ('nba') -> DB leagues.code ('NBA')."""
    return LEAGUES[league_key]["label"]


def sport_and_slug(league_key: str) -> tuple[str, str]:
    """'basketball/leagues/nba' -> ('basketball', 'nba') for the site API."""
    parts = LEAGUES[league_key]["path"].split("/")
    return parts[0], parts[-1]


def to_int(v):
    if v in (None, "", "-"):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (ValueError, TypeError):
        return None


def to_float(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def to_fraction(v):
    """TS%/pct that may arrive as '58.6' or '0.586' -> stored as a fraction."""
    f = to_float(v)
    if f is None:
        return None
    return f / 100.0 if f > 1.5 else f


@contextmanager
def log_run(source: str, entity_type: str, league_code_str: str | None = None):
    """
    Open an ingestion_log row, yield a mutable counter dict, and finalize the
    row on exit (success or error). Uses its own short-lived connections so the
    log is written even if the caller's transaction later rolls back.

        with log_run("espn", "players", "NBA") as c:
            ...
            c["read"] += 1
            c["upsert"] += 1
    """
    counter = {"read": 0, "upsert": 0, "notes": {}}
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO ingestion_log (source, entity_type, league_code, status)
               VALUES (%s, %s, %s, 'running') RETURNING id;""",
            (source, entity_type, league_code_str),
        )
        run_id = cur.fetchone()[0]
        cur.close()

    error = None
    try:
        yield counter
    except Exception as e:  # noqa: BLE001 — we re-raise after logging
        error = str(e)
        raise
    finally:
        import json
        status = "error" if error else "success"
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """UPDATE ingestion_log
                     SET status = %s,
                         records_read = %s,
                         records_upsert = %s,
                         finished_at = now(),
                         error = %s,
                         notes = %s
                   WHERE id = %s;""",
                (
                    status,
                    counter["read"],
                    counter["upsert"],
                    error,
                    json.dumps(counter["notes"]),
                    run_id,
                ),
            )
            cur.close()
        print(
            f"[ingestion_log #{run_id}] {entity_type} {league_code_str or ''} "
            f"-> {status}: read={counter['read']} upsert={counter['upsert']}"
            + (f" error={error}" if error else "")
        )
