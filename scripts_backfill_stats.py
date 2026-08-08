import sys
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from app.db import get_conn, query, log_ingestion
from scripts_seed_legends import LEGENDS

CORE = "https://sports.core.api.espn.com/v2/sports"
PATHS = {
    "NBA": "basketball/leagues/nba",
    "NFL": "football/leagues/nfl",
    "MLB": "baseball/leagues/mlb",
    "NHL": "hockey/leagues/nhl",
    "WNBA": "basketball/leagues/wnba",
}
RANGES = {
    "NBA": (1987, 2025), "NFL": (2002, 2025), "MLB": (1968, 2025),
    "NHL": (1980, 2025), "WNBA": (2000, 2025),
}


def fetch_season(args):
    path, aid, year = args
    try:
        u = f"{CORE}/{path}/seasons/{year}/types/2/athletes/{aid}/statistics"
        r = requests.get(u, timeout=12)
        if r.status_code != 200:
            return year, None
        d = r.json()
        flat = {}
        for cat in d.get("splits", {}).get("categories", []):
            cname = cat.get("name", "")
            for s in cat.get("stats", []):
                key = f"{cname}.{s.get('name')}"
                val = s.get("value")
                if val is not None:
                    flat[key] = val
        return year, (flat if flat else None)
    except Exception:
        return year, None


def backfill_player(player, code, season_map):
    path = PATHS[code]
    lo, hi = RANGES[code]
    years = list(range(hi, lo - 1, -1))
    aid = player["external_id"]

    tasks = [(path, aid, y) for y in years]
    rows = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for year, flat in pool.map(fetch_season, tasks):
            if not flat:
                continue
            sid = season_map.get(year)
            if not sid:
                continue
            gp = flat.get("general.gamesPlayed")
            per = flat.get("general.PER")
            ts = flat.get("offensive.trueShootingPct")
            rows.append((
                player["id"], sid,
                int(gp) if gp else None,
                json.dumps(flat),
                float(per) if per else None,
                float(ts) if ts else None,
            ))

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO player_seasons
                   (player_id, season_id, games_played, stats, per, true_shooting, source)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s,'espn')
                   ON CONFLICT (player_id, season_id) DO UPDATE SET
                       games_played = EXCLUDED.games_played,
                       stats = EXCLUDED.stats,
                       per = EXCLUDED.per,
                       true_shooting = EXCLUDED.true_shooting,
                       updated_at = now()""",
                rows,
            )
    return len(rows)


def run(code, mode="legends", limit=None):
    league = query("SELECT id FROM leagues WHERE code = %s", (code,))[0]
    lid = league["id"]

    seasons = query("SELECT id, year FROM seasons WHERE league_id = %s", (lid,))
    season_map = {s["year"]: s["id"] for s in seasons}

    if mode == "legends":
        names = LEGENDS.get(code, [])
        if not names:
            print("no legends list for", code)
            return 0
        players = query("""SELECT id, external_id, full_name FROM players
                           WHERE league_id = %s AND full_name = ANY(%s)
                           ORDER BY full_name""", (lid, names))
        if limit:
            players = players[:limit]
    elif mode == "active":
        players = query("""SELECT id, external_id, full_name FROM players
                           WHERE league_id = %s AND active = true
                           ORDER BY id LIMIT %s""", (lid, limit or 1000))
    else:
        players = query("""SELECT p.id, p.external_id, p.full_name FROM players p
                           LEFT JOIN player_seasons ps ON ps.player_id = p.id
                           WHERE p.league_id = %s AND ps.id IS NULL
                           ORDER BY p.id LIMIT %s""", (lid, limit or 500))

    print(f"[{code}/{mode}] {len(players)} players to process")

    total = 0
    for i, p in enumerate(players, 1):
        n = backfill_player(p, code, season_map)
        total += n
        if n:
            print(f"  {i}/{len(players)} {p['full_name'][:28]:28} {n} seasons")
        if i % 25 == 0:
            print(f"  --- {i}/{len(players)} done, {total} season rows ---")

    log_ingestion("espn", f"player_seasons/{mode}", lid, total, "success")
    print(f"[{code}] {total} season rows written")
    return total


if __name__ == "__main__":
    code = sys.argv[1].upper() if len(sys.argv) > 1 else "NBA"
    mode = sys.argv[2] if len(sys.argv) > 2 else "legends"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    run(code, mode, limit)
