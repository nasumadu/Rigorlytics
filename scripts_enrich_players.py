"""Fetch headshot and jersey for players that have season data."""

import sys
import requests
from concurrent.futures import ThreadPoolExecutor
from app.db import query, get_conn

PATHS = {
    "NBA": "basketball/leagues/nba",
    "NFL": "football/leagues/nfl",
    "MLB": "baseball/leagues/mlb",
    "NHL": "hockey/leagues/nhl",
    "WNBA": "basketball/leagues/wnba",
}


def fetch(args):
    pid, ext, path = args
    try:
        u = f"https://sports.core.api.espn.com/v2/sports/{path}/athletes/{ext}"
        r = requests.get(u, timeout=12)
        if r.status_code != 200:
            return None
        d = r.json()
        head = (d.get("headshot") or {}).get("href")
        jersey = d.get("jersey")
        pos = ((d.get("position") or {}).get("abbreviation"))
        return (head, str(jersey) if jersey else None, pos, pid)
    except Exception:
        return None


def run(code):
    path = PATHS[code]
    players = query("""
        SELECT DISTINCT p.id, p.external_id
        FROM players p
        JOIN leagues l ON l.id = p.league_id
        JOIN player_seasons ps ON ps.player_id = p.id
        WHERE l.code = %s AND p.headshot_url IS NULL
    """, (code,))
    print(f"[{code}] {len(players)} players to enrich")
    if not players:
        return 0

    tasks = [(p["id"], p["external_id"], path) for p in players]
    rows = []
    with ThreadPoolExecutor(max_workers=15) as pool:
        for res in pool.map(fetch, tasks):
            if res:
                rows.append(res)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """UPDATE players
                   SET headshot_url = %s,
                       jersey = %s,
                       position = COALESCE(%s, position)
                   WHERE id = %s""",
                rows,
            )
    print(f"[{code}] enriched {len(rows)}")
    return len(rows)


if __name__ == "__main__":
    target = sys.argv[1].upper() if len(sys.argv) > 1 else None
    codes = [target] if target else list(PATHS.keys())
    for c in codes:
        run(c)
