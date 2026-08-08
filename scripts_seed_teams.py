import requests
from app.db import get_conn, get_league_id, log_ingestion

ENDPOINTS = {
    "NBA":  "basketball/nba",
    "NFL":  "football/nfl",
    "MLB":  "baseball/mlb",
    "NHL":  "hockey/nhl",
    "WNBA": "basketball/wnba",
}


def fetch_teams(path):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams"
    r = requests.get(url, params={"limit": 100}, timeout=15)
    r.raise_for_status()
    data = r.json()
    out = []
    sports = data.get("sports", [])
    if not sports:
        return out
    leagues = sports[0].get("leagues", [])
    if not leagues:
        return out
    for entry in leagues[0].get("teams", []):
        t = entry.get("team", {})
        out.append({
            "external_id": t.get("id"),
            "name": t.get("displayName"),
            "abbreviation": t.get("abbreviation"),
            "city": t.get("location"),
        })
    return out


total = 0
for code, path in ENDPOINTS.items():
    lid = get_league_id(code)
    if not lid:
        print("missing league:", code)
        continue

    try:
        teams = fetch_teams(path)
    except Exception as e:
        print(code, "FETCH FAILED:", e)
        log_ingestion("espn", "teams", lid, 0, "failed", str(e))
        continue

    rows = [(lid, t["external_id"], t["name"], t["abbreviation"], t["city"])
            for t in teams if t.get("external_id") and t.get("name")]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO teams (league_id, external_id, name, abbreviation, city)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (league_id, external_id)
                   DO UPDATE SET name = EXCLUDED.name,
                                 abbreviation = EXCLUDED.abbreviation,
                                 city = EXCLUDED.city""",
                rows,
            )

    log_ingestion("espn", "teams", lid, len(rows), "success")
    print(f"{code:5} {len(rows):3} teams")
    total += len(rows)

print()
print("Total teams:", total)

with get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT l.code, count(*) AS n
            FROM teams t JOIN leagues l ON l.id = t.league_id
            GROUP BY l.code ORDER BY l.code
        """)
        for r in cur.fetchall():
            print(f"  {r['code']:5} {r['n']}")
