import re
import requests
from concurrent.futures import ThreadPoolExecutor

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
    "Career", "Careers", "Statistics", "Stat", "Numbers", "Record", "Records",
    "History", "Comparison", "Versus", "Vs", "And", "Or", "With", "Against",
    "Better", "Worse", "Greatest", "GOAT", "Prime", "Peak", "Rookie",
    "Playoff", "Playoffs", "Finals", "Championship", "MVP", "All",
    "Value", "Contract", "Salary", "Worth", "Analysis", "Breakdown",
    "Efficiency", "Advanced", "Metrics", "Per", "Average", "Averages",
    "Overall", "Total", "Totals", "League", "Leaders", "Rankings",
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



NFL_TEAMS = ["raiders", "chiefs", "49ers", "cowboys", "packers", "steelers", "patriots",
             "eagles", "giants", "jets", "bills", "dolphins", "ravens", "bengals",
             "browns", "texans", "colts", "jaguars", "titans", "broncos", "chargers",
             "commanders", "bears", "lions", "vikings", "falcons", "panthers", "saints",
             "buccaneers", "cardinals", "rams", "seahawks"]
NBA_TEAMS = ["lakers", "celtics", "warriors", "bulls", "heat", "knicks", "nets", "nuggets",
             "bucks", "suns", "mavericks", "clippers", "76ers", "sixers", "raptors",
             "hawks", "hornets", "cavaliers", "pistons", "pacers", "grizzlies", "timberwolves",
             "pelicans", "thunder", "magic", "blazers", "kings", "spurs", "jazz", "wizards", "rockets"]
MLB_TEAMS = ["yankees", "red sox", "dodgers", "giants", "cubs", "cardinals", "mets",
             "braves", "astros", "phillies", "padres", "mariners", "rangers", "blue jays",
             "orioles", "rays", "twins", "guardians", "tigers", "royals", "white sox",
             "angels", "athletics", "diamondbacks", "rockies", "brewers", "pirates",
             "reds", "marlins", "nationals"]
NHL_TEAMS = ["oilers", "penguins", "capitals", "bruins", "maple leafs", "canadiens",
             "rangers", "avalanche", "lightning", "golden knights", "panthers", "stars",
             "flames", "canucks", "jets", "wild", "predators", "blues", "sharks", "kraken"]
WNBA_TEAMS = ["fever", "aces", "liberty", "sky", "storm", "mercury", "sun", "lynx",
              "wings", "mystics", "dream", "sparks", "valkyries"]


def infer_leagues(subtitle):
    s = (subtitle or "").lower()
    if any(t in s for t in NFL_TEAMS):
        return ["nfl"]
    if any(t in s for t in WNBA_TEAMS):
        return ["wnba"]
    if any(t in s for t in NBA_TEAMS):
        return ["nba"]
    if any(t in s for t in MLB_TEAMS):
        return ["mlb"]
    if any(t in s for t in NHL_TEAMS):
        return ["nhl"]
    return []


def lookup_player(name):
    """Search ESPN, prefer exact matches, and verify the athlete has stats."""
    try:
        r = requests.get(SEARCH_URL, params={"query": name, "limit": 12}, timeout=10)
        data = r.json()

        target = name.strip().lower()
        suffixes = (" jr.", " jr", " sr.", " sr", " ii", " iii", " iv")
        query_has_suffix = any(target.endswith(s) for s in suffixes)

        candidates = []
        for res in data.get("results", []):
            if res.get("type") != "player":
                continue
            for c in res.get("contents", []):
                uid = c.get("uid", "")
                if "a:" not in uid:
                    continue
                athlete_id = uid.split("a:")[-1]
                dn = c.get("displayName", name)
                sub = c.get("subtitle", "")

                league_key = None
                for key, cfg in LEAGUES.items():
                    if cfg["uid"] in uid:
                        league_key = key
                        break

                # skip college results (l:23 etc) unless nothing else exists
                is_college = league_key is None and "l:" in uid

                exact = dn.strip().lower() == target
                dn_has_suffix = any(dn.strip().lower().endswith(s) for s in suffixes)
                suffix_penalty = 1 if (dn_has_suffix and not query_has_suffix) else 0

                score = 0
                if exact:
                    score -= 10
                score += suffix_penalty * 5
                if is_college:
                    score += 8
                if league_key is None:
                    score += 1

                candidates.append((score, league_key, athlete_id, dn, sub))

        if not candidates:
            return None, None, None, None

        candidates.sort(key=lambda x: x[0])

        # try each candidate in order, return the first that actually has stats
        for score, league_key, athlete_id, dn, sub in candidates[:5]:
            if league_key:
                leagues_to_try = [league_key]
            else:
                # infer league from the subtitle (team name) when uid has no league
                leagues_to_try = infer_leagues(sub)
            for lk in leagues_to_try:
                for probe in (2024, 2015, 2005, 1998, 1990):
                    if get_stats(lk, athlete_id, probe):
                        return lk, athlete_id, dn, sub

        top = candidates[0]
        return top[1], top[2], top[3], top[4]
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



CAREER_AVG_FIELDS = {
    "nba": [("offensive", "avgPoints", "PPG"), ("general", "avgRebounds", "RPG"),
            ("offensive", "avgAssists", "APG"), ("offensive", "fieldGoalPct", "FG%"),
            ("offensive", "threePointFieldGoalPct", "3P%"), ("offensive", "trueShootingPct", "TS%"),
            ("general", "PER", "PER")],
    "wnba": [("offensive", "avgPoints", "PPG"), ("general", "avgRebounds", "RPG"),
             ("offensive", "avgAssists", "APG"), ("offensive", "trueShootingPct", "TS%")],
    "nfl": [("receiving", "receptions", "Rec/season"), ("receiving", "receivingYards", "Rec Yds/season"),
            ("passing", "passingYards", "Pass Yds/season"), ("rushing", "rushingYards", "Rush Yds/season")],
    "mlb": [("batting", "avg", "AVG"), ("batting", "homeRuns", "HR/season"),
            ("batting", "OPS", "OPS"), ("pitching", "ERA", "ERA")],
    "nhl": [("offensive", "goals", "Goals/season"), ("offensive", "assists", "Assists/season"),
            ("offensive", "points", "Points/season")],
}


def compute_career(league_key, season_stats_list):
    """Average the per-game rate stats across all retrieved seasons."""
    fields = CAREER_AVG_FIELDS.get(league_key, [])
    if not fields or not season_stats_list:
        return ""
    out = []
    for cat, key, label in fields:
        vals = []
        for st in season_stats_list:
            raw = st.get(cat, {}).get(key)
            if raw in (None, "", "-"):
                continue
            try:
                vals.append(float(str(raw).replace(",", "").replace("%", "")))
            except Exception:
                continue
        if vals:
            avg = sum(vals) / len(vals)
            out.append("    " + label + ": " + ("%.1f" % avg))
    if not out:
        return ""
    n = len(season_stats_list)
    return "\n  CAREER AVERAGE (across " + str(n) + " seasons retrieved):\n" + "\n".join(out) + "\n"


def get_player_block(name, seasons=None):
    league_key, athlete_id, display, team = lookup_player(name)
    if not athlete_id:
        return ""

    cfg = LEAGUES.get(league_key, {})
    label = cfg.get("label", "")

    years = list(range(2025, 2005, -1))

    def fetch(y):
        return (y, get_stats(league_key, athlete_id, y))

    results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for y, stats in pool.map(fetch, years):
            if stats:
                results.append((y, stats))

    results.sort(key=lambda x: -x[0])

    collected = []
    for season, stats in results:
        line = format_stats(league_key, stats)
        if line:
            collected.append((season, stats, line))
        if len(collected) >= 12:
            break

    if not collected:
        return ""

    block = "\n" + label + " PLAYER: " + str(display) + "\n"
    if team:
        block += "Most recent team on record: " + str(team) + " (NOT necessarily the team for the seasons below)\n"
    block += "Seasons of data: " + str(len(collected)) + "\n"

    career = compute_career(league_key, [s for _, s, _ in collected])
    if career:
        block += career

    block += "\n  SEASON BY SEASON:\n"
    for season, _, line in collected:
        block += "\n  " + str(season) + ":\n" + line + "\n"

    return block


def search_all_players(question):
    names = extract_names(question)
    if not names:
        return ""
    context = ""
    with ThreadPoolExecutor(max_workers=4) as pool:
        for b in pool.map(get_player_block, names):
            if b:
                context += b
    return context
