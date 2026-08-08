import sys
import requests
from concurrent.futures import ThreadPoolExecutor
from app.db import get_conn, get_league_id, log_ingestion

CORE = "https://sports.core.api.espn.com/v2/sports"

PATHS = {
    "NBA":  "basketball/leagues/nba",
    "NFL":  "football/leagues/nfl",
    "MLB":  "baseball/leagues/mlb",
    "NHL":  "hockey/leagues/nhl",
    "WNBA": "basketball/leagues/wnba",
}


def list_athlete_urls(path, limit_pages=None):
    """Page through the athletes index and collect detail URLs."""
    urls = []
    page = 1
    while True:
        r = requests.get(f"{CORE}/{path}/athletes",
                         params={"limit": 1000, "page": page}, timeout=20)
        if r.status_code != 200:
            break
        data = r.json()
        items = data.get("items", [])
        if not items:
            break
        urls.extend(i.get("$ref") for i in items if i.get("$ref"))
        total_pages = data.get("pageCount", 1)
        if page >= total_pages:
            break
        if limit_pages and page >= limit_pages:
            break
        page += 1
    return urls


def fetch_athlete(url):
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        a = r.json()
        return {
            "external_id": str(a.get("id")),
            "full_name": a.get("displayName"),
            "position": (a.get("position") or {}).get("abbreviation"),
            "birth_date": (a.get("dateOfBirth") or "")[:10] or None,
            "height": a.get("height"),
            "weight": a.get("weight"),
            "active": a.get("active", False),
        }
    except Exception:
        return None


def seed_league(code, max_pages=None):
    lid = get_league_id(code)
    path = PATHS[code]

    print(f"[{code}] listing athletes...")
    urls = list_athlete_urls(path, max_pages)
    print(f"[{code}] {len(urls)} athlete records found")

    if not urls:
        log_ingestion("espn", "players", lid, 0, "failed", "no athletes returned")
        return 0

    players = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        for i, p in enumerate(pool.map(fetch_athlete, urls)):
            if p and p.get("external_id") and p.get("full_name"):
                players.append(p)
            if i and i % 500 == 0:
                print(f"  ...{i}/{len(urls)}")

    rows = [(lid, p["external_id"], p["full_name"], p["position"],
             p["birth_date"],
             int(p["height"]) if p.get("height") else None,
             int(p["weight"]) if p.get("weight") else None,
             p["active"])
            for p in players]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO players
                   (league_id, external_id, full_name, position, birth_date,
                    height_inches, weight_lbs, active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (league_id, external_id) DO UPDATE SET
                       full_name = EXCLUDED.full_name,
                       position = EXCLUDED.position,
                       birth_date = COALESCE(EXCLUDED.birth_date, players.birth_date),
                       height_inches = COALESCE(EXCLUDED.height_inches, players.height_inches),
                       weight_lbs = COALESCE(EXCLUDED.weight_lbs, players.weight_lbs),
                       active = EXCLUDED.active,
                       updated_at = now()""",
                rows,
            )

    log_ingestion("espn", "players", lid, len(rows), "success")
    print(f"[{code}] {len(rows)} players stored")
    return len(rows)


if __name__ == "__main__":
    target = sys.argv[1].upper() if len(sys.argv) > 1 else None
    codes = [target] if target else list(PATHS.keys())
    total = 0
    for c in codes:
        total += seed_league(c)
    print()
    print("Total players stored:", total)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT l.code, count(*) AS n
                           FROM players p JOIN leagues l ON l.id = p.league_id
                           GROUP BY l.code ORDER BY l.code""")
            for r in cur.fetchall():
                print(f"  {r['code']:5} {r['n']}")
