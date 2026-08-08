from app.db import get_conn, get_league_id

# Year ranges based on verified ESPN coverage
RANGES = {
    "NBA":  (1987, 2025),
    "NFL":  (2002, 2025),
    "MLB":  (1968, 2025),
    "NHL":  (1980, 2025),
    "WNBA": (2000, 2025),
}

rows = []
for code, (start, end) in RANGES.items():
    lid = get_league_id(code)
    if not lid:
        print("MISSING LEAGUE:", code)
        continue
    for year in range(start, end + 1):
        rows.append((lid, year, "regular"))

with get_conn() as conn:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO seasons (league_id, year, season_type)
               VALUES (%s, %s, %s)
               ON CONFLICT (league_id, year, season_type) DO NOTHING""",
            rows,
        )

with get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT l.code, count(*) AS seasons, min(s.year) AS earliest, max(s.year) AS latest
            FROM seasons s JOIN leagues l ON l.id = s.league_id
            GROUP BY l.code ORDER BY l.code
        """)
        for r in cur.fetchall():
            print(f"{r['code']:5} {r['seasons']:3} seasons  {r['earliest']}-{r['latest']}")
