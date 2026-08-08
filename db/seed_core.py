"""
seed_core.py — seed the static tables: leagues + seasons.

Idempotent: upserts on natural keys, safe to re-run.

Season coverage is seeded as a *superset* of what any single source provides,
because the DB is meant to hold historical data (e.g. pre-2002 NFL) sourced
separately from ESPN. Backfill jobs need season rows to exist first.

Run after schema.sql:
    python db/seed_core.py
"""
from __future__ import annotations

from db import get_conn

# code, name, sport, espn_slug, earliest_year, spans_two_years
LEAGUES = [
    ("NBA",  "National Basketball Association",   "basketball", "basketball/nba", 1980, True),
    ("WNBA", "Women's National Basketball Association", "basketball", "basketball/wnba", 1997, False),
    ("NFL",  "National Football League",          "football",   "football/nfl",   1970, False),
    ("MLB",  "Major League Baseball",             "baseball",   "baseball/mlb",   1968, False),
    ("NHL",  "National Hockey League",            "hockey",     "hockey/nhl",     1980, True),
]

THROUGH_YEAR = 2025  # inclusive ending year


def upsert_leagues(cur) -> dict[str, int]:
    ids: dict[str, int] = {}
    for code, name, sport, slug, _earliest, _spans in LEAGUES:
        cur.execute(
            """
            INSERT INTO leagues (code, name, sport, espn_slug)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE
              SET name = EXCLUDED.name,
                  sport = EXCLUDED.sport,
                  espn_slug = EXCLUDED.espn_slug
            RETURNING id;
            """,
            (code, name, sport, slug),
        )
        ids[code] = cur.fetchone()[0]
    return ids


def upsert_seasons(cur, league_ids: dict[str, int]) -> int:
    n = 0
    for code, _name, _sport, _slug, earliest, spans in LEAGUES:
        lid = league_ids[code]
        for year in range(earliest, THROUGH_YEAR + 1):
            label = f"{year - 1}-{str(year)[2:]}" if spans else str(year)
            cur.execute(
                """
                INSERT INTO seasons (league_id, year, label, season_type)
                VALUES (%s, %s, %s, 'regular')
                ON CONFLICT (league_id, year, season_type) DO UPDATE
                  SET label = EXCLUDED.label;
                """,
                (lid, year, label),
            )
            n += 1
    return n


def main() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        league_ids = upsert_leagues(cur)
        seasons = upsert_seasons(cur, league_ids)
        cur.close()
    print(f"leagues upserted: {len(league_ids)}  {league_ids}")
    print(f"seasons upserted: {seasons}")


if __name__ == "__main__":
    main()
