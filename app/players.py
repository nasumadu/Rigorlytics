import re
import requests

SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"

LEAGUES = {
    "nba": {"uid": "l:46", "path": "basketball/leagues/nba", "label": "NBA"},
    "nfl": {"uid": "l:28", "path": "football/leagues/nfl", "label": "NFL"},
    "mlb": {"uid": "l:10", "path": "baseball/leagues/mlb", "label": "MLB"},
    "nhl": {"uid": "l:90", "path": "hockey/leagues/nhl", "label": "NHL"},
    "wnba": {"uid": "l:59", "path": "basketball/leagues/wnba", "label": "WNBA"},
}

STOPWORDS = {
    "Who", "What", "When", "Where", "Why", "How", "Is", "Are", "Was", "Were",
    "Should", "Could", "Would", "Did", "Does", "Do", "Can", "Will", "The",
    "Compare", "Analyze", "Tell", "Give", "Show", "Best", "Worst", "Top",
    "NBA", "NFL", "MLB", "NHL", "WNBA", "PPG", "APG", "RPG", "TS", "PER",
    "Fantasy", "Betting", "Start", "Sit", "Trade", "Draft", "Contract",
    "Week", "Season", "Game", "Games", "Team", "Player", "Stats", "Points",
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
}


def extract_names(question):
    """Pull likely player names out of a question."""
    cleaned = re.sub(r"[?.,!;:]", " ", question)
    tokens = cleaned.split()

    candidates = []
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip("'\"")
        if not tok or not tok[0].isupper() or tok in STOPWORDS:
            i += 1
            continue

        parts = [tok]
        j = i + 1
        while j < len(tokens) and j < i + 3:
            nxt = tokens[j].strip("'\"")
            if nxt and nxt[0].isupper() and nxt not in STOPWORDS:
                parts.append(nxt)
                j += 1
            else:
                break

        phrase = " ".join(parts)
        if len(phrase) > 2:
            candidates.append(phrase)
        i = j if j > i else i + 1

    seen = set()
    out = []
    for c in candidates:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out[:4]


def lookup_player(name):
    """Search ESPN across all leagues. Returns (league_key, athlete_id, display, team)."""
    try:
        r = requests.get(SEARCH_URL, params={"query": name, "limit": 8}, timeout=10)
        data = r.json()
        for res in data.get("results", []):
            if res.get("type") != "player":
                continue
            for c in res.get("contents", []):
                uid = c.get("uid", "")
                if "a:" not in uid:
                    continue
                for key, cfg in LEAGUES.items():
                    if cfg["uid"] in uid:
                        return key, uid.split("a:")[-1], c.get("displayName", name), c.get("subtitle", "")
        return None, None, None, None
    except Exception:
        return None, None, None, None


def get_stats(league_key, athlete_id, season):
    cfg = LEAGUES.get(league_key)
    if not cfg:
        return None
    try:
        url = ("https://sports.core.api.espn.com/v2/sports/" + cfg["path"] +
               "/seasons/" + str(season) + "/types/2/athletes/" + str(athlete_id) + "/statistics")
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        cats = {}
        for cat in data.get("splits", {}).get("categories", []):
            vals = {}
            for s in cat.get("stats", []):
                vals[s.get("name")] = s.get("displayValue")
            cats[cat.get("name", "")] = vals
        return cats
    except Exception:
        return None


FIELD_MAP = {
    "nba": [
        ("general", "gamesPlayed", "Games"),
        ("offensive", "avgPoints", "PPG"),
        ("general", "avgRebounds", "RPG"),
        ("offensive", "avgAssists", "APG"),
        ("defensive", "avgSteals", "SPG"),
        ("defensive", "avgBlocks", "BPG"),
        ("offensive", "avgMinutes", "MPG"),
        ("offensive", "fieldGoalPct", "FG%"),
        ("offensive", "threePointFieldGoalPct", "3P%"),
        ("offensive", "freeThrowPct", "FT%"),
        ("offensive", "effectiveFGPct", "eFG%"),
        ("offensive", "trueShootingPct", "TS%"),
        ("general", "PER", "PER"),
    ],
    "wnba": [
        ("general", "gamesPlayed", "Games"),
        ("offensive", "avgPoints", "PPG"),
        ("general", "avgRebounds", "RPG"),
        ("offensive", "avgAssists", "APG"),
        ("offensive", "fieldGoalPct", "FG%"),
        ("offensive", "threePointFieldGoalPct", "3P%"),
        ("offensive", "trueShootingPct", "TS%"),
        ("general", "PER", "PER"),
    ],
    "nfl": [
        ("general", "gamesPlayed", "Games"),
        ("passing", "passingYards", "Pass Yds"),
        ("passing", "passingTouchdowns", "Pass TD"),
        ("passing", "interceptions", "INT"),
        ("passing", "completionPct", "Comp %"),
        ("passing", "QBRating", "Passer Rating"),
        ("rushing", "rushingYards", "Rush Yds"),
        ("rushing", "rushingTouchdowns", "Rush TD"),
        ("rushing", "yardsPerRushAttempt", "Yds/Carry"),
        ("receiving", "receptions", "Receptions"),
        ("receiving", "receivingYards", "Rec Yds"),
        ("receiving", "receivingTouchdowns", "Rec TD"),
        ("receiving", "receivingTargets", "Targets"),
        ("receiving", "yardsPerReception", "Yds/Rec"),
        ("defensive", "totalTackles", "Tackles"),
        ("defensive", "sacks", "Sacks"),
    ],
    "mlb": [
        ("general", "gamesPlayed", "Games"),
        ("batting", "avg", "AVG"),
        ("batting", "homeRuns", "HR"),
        ("batting", "RBIs", "RBI"),
        ("batting", "runs", "Runs"),
        ("batting", "hits", "Hits"),
        ("batting", "OPS", "OPS"),
        ("batting", "onBasePct", "OBP"),
        ("batting", "slugAvg", "SLG"),
        ("batting", "stolenBases", "SB"),
        ("pitching", "ERA", "ERA"),
        ("pitching", "wins", "W"),
        ("pitching", "losses", "L"),
        ("pitching", "strikeouts", "K"),
        ("pitching", "WHIP", "WHIP"),
        ("pitching", "inningsPitched", "IP"),
        ("pitching", "saves", "SV"),
    ],
    "nhl": [
        ("general", "gamesPlayed", "Games"),
        ("offensive", "goals", "Goals"),
        ("offensive", "assists", "Assists"),
        ("offensive", "points", "Points"),
        ("offensive", "plusMinus", "+/-"),
        ("offensive", "powerPlayGoals", "PP Goals"),
        ("offensive", "shotsTotal", "Shots"),
        ("offensive", "shootingPct", "Shooting %"),
        ("goalie", "savePct", "Save %"),
        ("goalie", "goalsAgainstAverage", "GAA"),
        ("goalie", "shutouts", "Shutouts"),
    ],
}


def format_stats(league_key, stats):
    fields = FIELD_MAP.get(league_key, [])
    out = []
    for cat, key, label in fields:
        v = stats.get(cat, {}).get(key)
        if v not in (None, "", "0", "0.0", "-", "0.00"):
            out.append("    " + label + ": " + str(v))
    return "\n".join(out)


def get_player_block(name, seasons=None):
    league_key, athlete_id, display, team = lookup_player(name)
    if not athlete_id:
        return ""

    cfg = LEAGUES.get(league_key, {})
    label = cfg.get("label", "")

    if seasons is None:
        seasons = [2025, 2024, 2023]

    block = "\n" + label + " PLAYER: " + str(display) + "\n"
    if team:
        block += "Team: " + str(team) + "\n"

    found = False
    for season in seasons:
        stats = get_stats(league_key, athlete_id, season)
        if not stats:
            continue
        line = format_stats(league_key, stats)
        if not line:
            continue
        found = True
        block += "\n  " + str(season) + " SEASON:\n" + line + "\n"

    if not found:
        for season in [2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014,
                       2013, 2012, 2011, 2010, 2009, 2008]:
            stats = get_stats(league_key, athlete_id, season)
            if not stats:
                continue
            line = format_stats(league_key, stats)
            if not line:
                continue
            found = True
            block += "\n  " + str(season) + " SEASON:\n" + line + "\n"
            if block.count("SEASON:") >= 4:
                break

    return block if found else ""


def search_all_players(question):
    """Extract names from a question and pull stats for each."""
    names = extract_names(question)
    context = ""
    for n in names:
        b = get_player_block(n)
        if b:
            context += b
    return context
