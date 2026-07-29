import requests

SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"
CORE_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"


def find_player_id(name):
    """Search ESPN for an NFL player and return their athlete ID"""
    try:
        r = requests.get(SEARCH_URL, params={"query": name, "limit": 5}, timeout=10)
        data = r.json()
        for res in data.get("results", []):
            if res.get("type") != "player":
                continue
            for c in res.get("contents", []):
                uid = c.get("uid", "")
                if "l:28" in uid and "a:" in uid:
                    athlete_id = uid.split("a:")[-1]
                    return athlete_id, c.get("displayName", name), c.get("subtitle", "")
        return None, None, None
    except Exception:
        return None, None, None


def get_season_stats(athlete_id, season):
    """Pull season statistics for an NFL player"""
    try:
        url = f"{CORE_URL}/seasons/{season}/types/2/athletes/{athlete_id}/statistics"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        cats = {}
        for cat in data.get("splits", {}).get("categories", []):
            name = cat.get("name", "")
            stats = {}
            for s in cat.get("stats", []):
                stats[s.get("name")] = s.get("displayValue")
            cats[name] = stats
        return cats
    except Exception:
        return None


def format_receiving(stats):
    r = stats.get("receiving", {})
    if not r:
        return ""
    out = []
    fields = [
        ("receptions", "Receptions"),
        ("receivingYards", "Receiving Yards"),
        ("receivingTouchdowns", "Receiving TDs"),
        ("receivingTargets", "Targets"),
        ("yardsPerReception", "Yards Per Reception"),
        ("receivingYardsPerGame", "Receiving Yards Per Game"),
        ("longReception", "Longest Reception"),
        ("receivingFirstDowns", "Receiving First Downs"),
        ("receivingBigPlays", "Big Plays (20+ yds)"),
    ]
    for key, label in fields:
        if key in r and r[key] not in (None, "", "0"):
            out.append(f"    {label}: {r[key]}")
    return "\n".join(out)


def format_passing(stats):
    p = stats.get("passing", {})
    if not p:
        return ""
    out = []
    fields = [
        ("completions", "Completions"),
        ("passingAttempts", "Attempts"),
        ("completionPct", "Completion %"),
        ("passingYards", "Passing Yards"),
        ("passingTouchdowns", "Passing TDs"),
        ("interceptions", "Interceptions"),
        ("QBRating", "Passer Rating"),
        ("ESPNQBRating", "ESPN QBR"),
        ("passingYardsPerGame", "Yards Per Game"),
        ("yardsPerPassAttempt", "Yards Per Attempt"),
        ("sacks", "Sacks Taken"),
    ]
    for key, label in fields:
        if key in p and p[key] not in (None, "", "0"):
            out.append(f"    {label}: {p[key]}")
    return "\n".join(out)


def format_rushing(stats):
    ru = stats.get("rushing", {})
    if not ru:
        return ""
    out = []
    fields = [
        ("rushingAttempts", "Rushing Attempts"),
        ("rushingYards", "Rushing Yards"),
        ("rushingTouchdowns", "Rushing TDs"),
        ("yardsPerRushAttempt", "Yards Per Carry"),
        ("rushingYardsPerGame", "Rushing Yards Per Game"),
        ("longRushing", "Longest Rush"),
        ("rushingFirstDowns", "Rushing First Downs"),
    ]
    for key, label in fields:
        if key in ru and ru[key] not in (None, "", "0"):
            out.append(f"    {label}: {ru[key]}")
    return "\n".join(out)


def format_defensive(stats):
    d = stats.get("defensive", {})
    if not d:
        return ""
    out = []
    fields = [
        ("totalTackles", "Total Tackles"),
        ("soloTackles", "Solo Tackles"),
        ("sacks", "Sacks"),
        ("tacklesForLoss", "Tackles For Loss"),
        ("passesDefended", "Passes Defended"),
        ("QBHits", "QB Hits"),
    ]
    for key, label in fields:
        if key in d and d[key] not in (None, "", "0"):
            out.append(f"    {label}: {d[key]}")
    ints = stats.get("defensiveInterceptions", {})
    if ints.get("interceptions") not in (None, "", "0"):
        out.append(f"    Interceptions: {ints.get('interceptions')}")
    return "\n".join(out)


def get_player_stats(name, seasons=None):
    """Get full NFL stats for a player across multiple seasons"""
    if seasons is None:
        seasons = [2025, 2024, 2023]

    athlete_id, display_name, subtitle = find_player_id(name)
    if not athlete_id:
        return ""

    context = f"\nNFL PLAYER: {display_name}\n"
    if subtitle:
        context += f"Team/Position: {subtitle}\n"

    found_any = False
    for season in seasons:
        stats = get_season_stats(athlete_id, season)
        if not stats:
            continue

        blocks = []
        for fmt in (format_passing, format_rushing, format_receiving, format_defensive):
            b = fmt(stats)
            if b:
                blocks.append(b)

        if not blocks:
            continue

        found_any = True
        gp = stats.get("general", {}).get("gamesPlayed", "")
        context += f"\n  {season} SEASON"
        if gp:
            context += f" (Games Played: {gp})"
        context += ":\n"
        context += "\n".join(blocks) + "\n"

    if not found_any:
        return ""
    return context


NFL_NAMES = [
    "Mahomes", "Allen", "Hurts", "Burrow", "Lawrence", "Herbert", "Jackson",
    "Stroud", "Young", "Richardson", "Prescott", "Goff", "Love", "Purdy",
    "Tagovailoa", "Daniels", "Maye", "Nix", "Penix", "Rodgers", "Stafford",
    "McCaffrey", "Henry", "Barkley", "Gibbs", "Robinson", "Taylor", "Jacobs",
    "Achane", "Hall", "Walker", "Etienne", "Pacheco", "Mixon", "Williams",
    "Jefferson", "Chase", "Hill", "Lamb", "Adams", "Diggs", "Brown", "Waddle",
    "Wilson", "London", "Olave", "Smith", "Higgins", "Kupp", "Metcalf",
    "Nabers", "Odunze", "Harrison", "McConkey", "Bowers", "Kelce", "Andrews",
    "Kittle", "LaPorta", "Pitts", "Hockenson", "Njoku",
    "Garrett", "Watt", "Parsons", "Bosa", "Donald", "Hutchinson", "Anderson",
    "Crosby", "Sweat", "Hendrickson", "Wagner", "Warner", "Ramsey", "Surtain",
    "Sauce", "Gardner", "Diggs", "Fitzpatrick", "Hamlin", "Byard",
    "Brady", "Manning", "Rice", "Sanders", "Moss", "Owens", "Gronkowski",
    "Tomlinson", "Peterson", "Favre", "Montana", "Marino", "Elway",
]


def search_nfl_data(question):
    """Detect NFL players in a question and return their statistics"""
    context = ""
    seen = set()
    q_lower = question.lower()

    for name in NFL_NAMES:
        if name.lower() in q_lower and name.lower() not in seen:
            seen.add(name.lower())
            stats = get_player_stats(name)
            if stats:
                context += stats
            if len(seen) >= 4:
                break

    return context
