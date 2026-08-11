"""Backfill season stats for specific players by name."""

import sys
from app.db import query
from scripts_backfill_stats import backfill_player, PATHS


def backfill_names(code, names):
    league = query("SELECT id FROM leagues WHERE code = %s", (code,))[0]
    lid = league["id"]
    seasons = query("SELECT id, year FROM seasons WHERE league_id = %s", (lid,))
    season_map = {s["year"]: s["id"] for s in seasons}

    total = 0
    for name in names:
        players = query("""SELECT id, external_id, full_name, position
                           FROM players
                           WHERE league_id = %s AND lower(full_name) = lower(%s)""",
                        (lid, name))
        if not players:
            print(f"  {name:24} NOT IN PLAYERS TABLE")
            continue
        for p in players:
            n = backfill_player(p, code, season_map)
            total += n
            pos = p.get("position") or "-"
            print(f"  {p['full_name']:24} {pos:4} {n} seasons")
    return total


if __name__ == "__main__":
    code = sys.argv[1].upper()
    names = sys.argv[2:]
    print(f"[{code}] backfilling {len(names)} names")
    t = backfill_names(code, names)
    print("rows written:", t)
