"""
ingest_players.py — enumerate players via each team's ESPN roster and upsert
into `players` (keyed on (source, external_id) = ESPN athlete id).

Roster enumeration gives a clean, bounded player pool to upsert; season stats
are filled separately by backfill_player_seasons.py (which reuses
app.players.get_stats).

Usage:
    python db/ingest_players.py                # all leagues
    python db/ingest_players.py --league nba   # one league (players.py key)
"""
from __future__ import annotations

import os
import sys

# make `app` importable before importing it (run from project root or not)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from concurrent.futures import ThreadPoolExecutor

import requests

from app.players import LEAGUES
from db import get_conn
from ingest_util import sport_and_slug, league_code, log_run

SITE_API = "https://site.api.espn.com/apis/site/v2/sports"


def fetch_roster(league_key: str, team_external_id: str) -> list[dict]:
    sport, slug = sport_and_slug(league_key)
    url = f"{SITE_API}/{sport}/{slug}/teams/{team_external_id}/roster"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return []
    data = r.json()
    athletes: list[dict] = []
    for node in data.get("athletes", []):
        # NFL groups athletes ({position, items:[...]}); NBA/MLB/NHL are flat.
        if isinstance(node, dict) and "items" in node:
            athletes.extend(node.get("items", []))
        elif isinstance(node, dict):
            athletes.append(node)
    return athletes


def _birth_date(a: dict):
    raw = a.get("dateOfBirth") or ""
    # e.g. "1994-02-19T08:00Z" -> "1994-02-19"
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return None


def upsert_player(cur, league_id: int, a: dict) -> None:
    pos = (a.get("position") or {}).get("abbreviation")
    headshot = (a.get("headshot") or {}).get("href")
    height = a.get("height")
    weight = a.get("weight")
    cur.execute(
        """
        INSERT INTO players (source, external_id, league_id, full_name,
                             first_name, last_name, position, jersey,
                             birth_date, height_in, weight_lb, active,
                             headshot_url)
        VALUES ('espn', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, external_id) DO UPDATE
          SET league_id    = EXCLUDED.league_id,
              full_name    = EXCLUDED.full_name,
              first_name   = EXCLUDED.first_name,
              last_name    = EXCLUDED.last_name,
              position     = EXCLUDED.position,
              jersey       = EXCLUDED.jersey,
              birth_date   = COALESCE(EXCLUDED.birth_date, players.birth_date),
              height_in    = COALESCE(EXCLUDED.height_in, players.height_in),
              weight_lb    = COALESCE(EXCLUDED.weight_lb, players.weight_lb),
              active       = EXCLUDED.active,
              headshot_url = COALESCE(EXCLUDED.headshot_url, players.headshot_url);
        """,
        (
            str(a["id"]),
            league_id,
            a.get("fullName") or a.get("displayName"),
            a.get("firstName"),
            a.get("lastName"),
            pos,
            a.get("jersey"),
            _birth_date(a),
            int(height) if isinstance(height, (int, float)) else None,
            int(weight) if isinstance(weight, (int, float)) else None,
            bool(a.get("active", True)),
            headshot,
        ),
    )


def teams_for_league(cur, league_id: int) -> list[str]:
    cur.execute(
        "SELECT external_id FROM teams WHERE league_id = %s AND source = 'espn';",
        (league_id,),
    )
    return [row[0] for row in cur.fetchall()]


def league_id_map(cur) -> dict[str, int]:
    cur.execute("SELECT code, id FROM leagues;")
    return {code: lid for code, lid in cur.fetchall()}


def ingest_league(league_key: str, league_id: int) -> None:
    code = league_code(league_key)
    with get_conn() as conn:
        cur = conn.cursor()
        team_ids = teams_for_league(cur, league_id)
        cur.close()
    if not team_ids:
        print(f"skip {code}: no teams — run seed_teams.py first")
        return

    with log_run("espn", "players", code) as c:
        # fetch rosters in parallel, upsert serially (psycopg2 conn isn't shared)
        with ThreadPoolExecutor(max_workers=8) as pool:
            rosters = list(
                pool.map(lambda tid: fetch_roster(league_key, tid), team_ids)
            )
        seen: set[str] = set()
        with get_conn() as conn:
            cur = conn.cursor()
            for roster in rosters:
                for a in roster:
                    aid = str(a.get("id") or "")
                    if not aid or aid in seen:
                        continue
                    seen.add(aid)
                    c["read"] += 1
                    upsert_player(cur, league_id, a)
                    c["upsert"] += 1
            cur.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=list(LEAGUES.keys()),
                    help="limit to one league (players.py key, e.g. nba)")
    args = ap.parse_args()

    with get_conn() as conn:
        cur = conn.cursor()
        codes = league_id_map(cur)
        cur.close()

    keys = [args.league] if args.league else list(LEAGUES.keys())
    for lk in keys:
        lid = codes.get(league_code(lk))
        if lid is None:
            print(f"skip {lk}: run seed_core.py first")
            continue
        ingest_league(lk, lid)


if __name__ == "__main__":
    main()
