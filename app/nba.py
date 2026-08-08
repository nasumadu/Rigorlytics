import requests

SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"
CORE_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"


def find_player_id(name):
    try:
        r = requests.get(SEARCH_URL, params={"query": name, "limit": 5}, timeout=10)
        data = r.json()
        for res in data.get("results", []):
            if res.get("type") != "player":
                continue
            for c in res.get("contents", []):
                uid = c.get("uid", "")
                if "l:46" in uid and "a:" in uid:
                    return uid.split("a:")[-1], c.get("displayName", name), c.get("subtitle", "")
        return None, None, None
    except Exception:
        return None, None, None


def get_season_stats(athlete_id, season):
    try:
        url = CORE_URL + "/seasons/" + str(season) + "/types/2/athletes/" + str(athlete_id) + "/statistics"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        cats = {}
        for cat in data.get("splits", {}).get("categories", []):
            stats = {}
            for s in cat.get("stats", []):
                stats[s.get("name")] = s.get("displayValue")
            cats[cat.get("name", "")] = stats
        return cats
    except Exception:
        return None


def format_season(stats):
    gen = stats.get("general", {})
    off = stats.get("offensive", {})
    dfn = stats.get("defensive", {})

    lines = []
    pairs = [
        (gen, "gamesPlayed", "Games Played"),
        (off, "avgPoints", "Points Per Game"),
        (gen, "avgRebounds", "Rebounds Per Game"),
        (off, "avgAssists", "Assists Per Game"),
        (dfn, "avgSteals", "Steals Per Game"),
        (dfn, "avgBlocks", "Blocks Per Game"),
        (off, "avgTurnovers", "Turnovers Per Game"),
        (off, "avgMinutes", "Minutes Per Game"),
        (off, "fieldGoalPct", "Field Goal %"),
        (off, "threePointFieldGoalPct", "3-Point %"),
        (off, "freeThrowPct", "Free Throw %"),
        (off, "effectiveFGPct", "Effective FG %"),
        (off, "trueShootingPct", "True Shooting %"),
        (gen, "PER", "PER"),
        (off, "points", "Total Points"),
        (gen, "rebounds", "Total Rebounds"),
        (off, "assists", "Total Assists"),
    ]
    for src, key, label in pairs:
        v = src.get(key)
        if v not in (None, "", "0", "0.0", "-"):
            lines.append("    " + label + ": " + str(v))
    return "\n".join(lines)


def get_player_stats(name, seasons=None):
    if seasons is None:
        seasons = [2025, 2024, 2023]

    athlete_id, display_name, subtitle = find_player_id(name)
    if not athlete_id:
        return ""

    context = "\nNBA PLAYER: " + str(display_name) + "\n"
    if subtitle:
        context += "Team: " + str(subtitle) + "\n"

    found = False
    for season in seasons:
        stats = get_season_stats(athlete_id, season)
        if not stats:
            continue
        block = format_season(stats)
        if not block:
            continue
        found = True
        context += "\n  " + str(season) + " SEASON:\n" + block + "\n"

    return context if found else ""


NBA_NAMES = [
    "Jokic", "Doncic", "Luka", "Embiid", "Giannis", "Antetokounmpo",
    "Tatum", "Brown", "Curry", "Durant", "LeBron", "James", "Davis",
    "Booker", "Beal", "Morant", "Ja Morant", "Edwards", "Anthony Edwards",
    "Mitchell", "Garland", "Haliburton", "Brunson", "Randle", "Towns",
    "Sabonis", "Fox", "Murray", "Porter", "Gordon", "Butler", "Adebayo",
    "Herro", "Banchero", "Wagner", "Wembanyama", "Wemby", "Holmgren",
    "Gilgeous-Alexander", "Shai", "SGA", "Williamson", "Zion", "Ingram",
    "Leonard", "Kawhi", "George", "Harden", "Westbrook", "Lillard",
    "Middleton", "Siakam", "Barnes", "Maxey", "Trae", "Young",
    "Jordan", "Kobe", "Bryant", "Shaq", "O'Neal", "Duncan", "Garnett",
    "Nowitzki", "Wade", "Pierce", "Nash", "Iverson", "Carter", "McGrady",
    "Pippen", "Rodman", "Malone", "Stockton", "Barkley", "Ewing",
    "Olajuwon", "Robinson", "Bird", "Magic", "Johnson", "Kareem",
]


def search_player_data(question):
    context = ""
    seen = set()
    q = question.lower()

    for name in NBA_NAMES:
        n = name.lower()
        if n in q and n not in seen:
            seen.add(n)
            stats = get_player_stats(name)
            if stats:
                context += stats
            if len(seen) >= 3:
                break

    return context if context else "No specific NBA player data found."
