"""
seed_teams.py — pull teams for every league from ESPN's site API and upsert
into `teams` (keyed on (source, external_id)).

This is genuinely new data (players.py doesn't fetch teams), so no reuse of the
lookup logic — just the LEAGUES config for slugs.

Run after seed_core.py:
    python db/seed_teams.py
"""
from __future__ import annotations

import os
import sys

# make `app` importable before importing it (run from project root or not)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from app.players import LEAGUES
from db import get_conn
from ingest_util import sport_and_slug, league_code, log_run

SITE_API = "https://site.api.espn.com/apis/site/v2/sports"


def fetch_teams(league_key: str) -> list[dict]:
    sport, slug = sport_and_slug(league_key)
    url = f"{SITE_API}/{sport}/{slug}/teams"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    out = []
    for sp in data.get("sports", []):
        for lg in sp.get("leagues", []):
            for entry in lg.get("teams", []):
                t = entry.get("team", {})
                if t.get("id"):
                    out.append(t)
    return out


def upsert_team(cur, league_id: int, t: dict) -> None:
    cur.execute(
        """
        INSERT INTO teams (league_id, source, external_id, abbreviation,
                           location, name, display_name, active)
        VALUES (%s, 'espn', %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, external_id) DO UPDATE
          SET league_id    = EXCLUDED.league_id,
              abbreviation = EXCLUDED.abbreviation,
              location     = EXCLUDED.location,
              name         = EXCLUDED.name,
              display_name = EXCLUDED.display_name,
              active       = EXCLUDED.active;
        """,
        (
            league_id,
            str(t["id"]),
            t.get("abbreviation"),
            t.get("location"),
            t.get("name"),
            t.get("displayName"),
            bool(t.get("isActive", True)),
        ),
    )


def league_id_map(cur) -> dict[str, int]:
    cur.execute("SELECT code, id FROM leagues;")
    return {code: lid for code, lid in cur.fetchall()}


def main() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        codes = league_id_map(cur)
        cur.close()

    for lk in LEAGUES:
        code = league_code(lk)
        lid = codes.get(code)
        if lid is None:
            print(f"skip {code}: run seed_core.py first")
            continue
        with log_run("espn", "teams", code) as c:
            teams = fetch_teams(lk)
            c["read"] = len(teams)
            with get_conn() as conn:
                cur = conn.cursor()
                for t in teams:
                    upsert_team(cur, lid, t)
                    c["upsert"] += 1
                cur.close()


if __name__ == "__main__":
    main()
