"""Add players to the database on demand via ESPN search."""

import sys
from app.db import query, get_conn, get_league_id
from app.players import lookup_player
from scripts_backfill_stats import backfill_player

LEAGUE_OF = {"nba": "NBA", "nfl": "NFL", "mlb": "MLB", "nhl": "NHL", "wnba": "WNBA"}


def add_player(name):
    league_key, aid, display, team = lookup_player(name)
    if not aid or not league_key:
        return None, f"{name}: not found on ESPN"

    code = LEAGUE_OF.get(league_key)
    lid = get_league_id(code)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO players (league_id, external_id, full_name, active)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (league_id, external_id) DO UPDATE SET
                               full_name = EXCLUDED.full_name
                           RETURNING id""", (lid, str(aid), display, True))
            pid = cur.fetchone()["id"]

    seasons = query("SELECT id, year FROM seasons WHERE league_id = %s", (lid,))
    season_map = {s["year"]: s["id"] for s in seasons}
    p = {"id": pid, "external_id": str(aid), "full_name": display}
    n = backfill_player(p, code, season_map)

    return (display, code, n), None


if __name__ == "__main__":
    for name in sys.argv[1:]:
        res, err = add_player(name)
        if err:
            print(" ", err)
        else:
            print(f"  {res[0]:26} {res[1]:5} {res[2]} seasons")
