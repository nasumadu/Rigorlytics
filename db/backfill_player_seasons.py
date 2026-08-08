"""
backfill_player_seasons.py — for every player in the DB, pull season-by-season
stats from ESPN and upsert into `player_seasons`.

Reuses app.players.get_stats verbatim (same endpoint, same parsing that already
powers the live site), so ingested lines match what users see today. The raw
category dict is stored as JSONB `stats`; PER and TS% are promoted to columns
for fast leaderboards; games_played is pulled out too.

Usage:
    python db/backfill_player_seasons.py --league nba
    python db/backfill_player_seasons.py --league nba --limit 25   # smoke test
    python db/backfill_player_seasons.py                           # all leagues
"""
from __future__ import annotations

import os
import sys

# make `app` importable before importing it (run from project root or not)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from concurrent.futures import ThreadPoolExecutor

from psycopg2.extras import Json

from app.players import LEAGUES, get_stats
from db import get_conn
from ingest_util import (
    league_code, log_run, to_int, to_float, to_fraction,
    ESPN_EARLIEST, CURRENT_SEASON,
)


def season_id_map(cur, league_id: int) -> dict[int, int]:
    """year -> season_id for a league's regular seasons."""
    cur.execute(
        """SELECT year, id FROM seasons
            WHERE league_id = %s AND season_type = 'regular';""",
        (league_id,),
    )
    return {year: sid for year, sid in cur.fetchall()}


def players_for_league(cur, league_id: int, limit: int | None):
    q = ("SELECT id, external_id FROM players "
         "WHERE league_id = %s ORDER BY id")
    params = [league_id]
    if limit:
        q += " LIMIT %s"
        params.append(limit)
    cur.execute(q, params)
    return cur.fetchall()


def promoted_metrics(league_key: str, stats: dict):
    """Return (games_played, per, true_shooting) from a get_stats() result."""
    general = stats.get("general", {})
    offensive = stats.get("offensive", {})
    gp = to_int(general.get("gamesPlayed"))
    per = tsp = None
    if league_key in ("nba", "wnba"):
        per = to_float(general.get("PER"))
        tsp = to_fraction(offensive.get("trueShootingPct"))
    return gp, per, tsp


def backfill_player(league_key, athlete_id, years):
    """Fetch all seasons for one athlete in parallel; return [(year, stats)]."""
    def fetch(y):
        return (y, get_stats(league_key, athlete_id, y))

    out = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for y, stats in pool.map(fetch, years):
            if stats:
                out.append((y, stats))
    return out


def upsert_season(cur, player_id, season_id, league_id, league_key, stats):
    gp, per, tsp = promoted_metrics(league_key, stats)
    cur.execute(
        """
        INSERT INTO player_seasons
            (player_id, season_id, league_id, games_played, stats, per, true_shooting)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_id, season_id) DO UPDATE
          SET league_id     = EXCLUDED.league_id,
              games_played  = EXCLUDED.games_played,
              stats         = EXCLUDED.stats,
              per           = EXCLUDED.per,
              true_shooting = EXCLUDED.true_shooting;
        """,
        (player_id, season_id, league_id, gp, Json(stats), per, tsp),
    )


def ingest_league(league_key: str, league_id: int, limit: int | None) -> None:
    code = league_code(league_key)
    years = list(range(ESPN_EARLIEST[league_key], CURRENT_SEASON + 1))

    with get_conn() as conn:
        cur = conn.cursor()
        smap = season_id_map(cur, league_id)
        players = players_for_league(cur, league_id, limit)
        cur.close()

    if not players:
        print(f"skip {code}: no players — run ingest_players.py first")
        return

    with log_run("espn", "player_seasons", code) as c:
        c["notes"] = {"players": len(players), "year_range": [years[0], years[-1]]}
        for pid, aid in players:
            seasons = backfill_player(league_key, aid, years)
            if not seasons:
                continue
            with get_conn() as conn:
                cur = conn.cursor()
                for year, stats in seasons:
                    sid = smap.get(year)
                    if sid is None:
                        continue  # no season row (shouldn't happen post-seed)
                    c["read"] += 1
                    upsert_season(cur, pid, sid, league_id, league_key, stats)
                    c["upsert"] += 1
                cur.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=list(LEAGUES.keys()))
    ap.add_argument("--limit", type=int, default=None,
                    help="max players per league (smoke testing)")
    args = ap.parse_args()

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT code, id FROM leagues;")
        codes = {code: lid for code, lid in cur.fetchall()}
        cur.close()

    keys = [args.league] if args.league else list(LEAGUES.keys())
    for lk in keys:
        lid = codes.get(league_code(lk))
        if lid is None:
            print(f"skip {lk}: run seed_core.py first")
            continue
        ingest_league(lk, lid, args.limit)


if __name__ == "__main__":
    main()
