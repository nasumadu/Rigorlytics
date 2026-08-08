import requests
from datetime import datetime, timedelta


def get_mlb_games(date_str=None):
    try:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        url = "https://statsapi.mlb.com/api/v1/schedule"
        r = requests.get(url, params={"sportId": 1, "date": date_str, "hydrate": "team,linescore"}, timeout=10)
        data = r.json()
        games = []
        for d in data.get("dates", []):
            for g in d.get("games", []):
                away = g.get("teams", {}).get("away", {})
                home = g.get("teams", {}).get("home", {})
                line = g.get("linescore", {})
                games.append({
                    "away": away.get("team", {}).get("name", ""),
                    "home": home.get("team", {}).get("name", ""),
                    "away_abbr": away.get("team", {}).get("abbreviation", ""),
                    "home_abbr": home.get("team", {}).get("abbreviation", ""),
                    "away_score": away.get("score"),
                    "home_score": home.get("score"),
                    "status": g.get("status", {}).get("detailedState", ""),
                    "detail": (line.get("currentInningOrdinal", "") if "progress" in g.get("status", {}).get("detailedState", "").lower() else g.get("status", {}).get("detailedState", "")),
                })
        return games
    except Exception:
        return []


def get_nhl_games(date_str=None):
    try:
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        url = "https://api-web.nhle.com/v1/schedule/" + date_str
        r = requests.get(url, timeout=10)
        data = r.json()
        games = []
        for week in data.get("gameWeek", []):
            if week.get("date") != date_str:
                continue
            for g in week.get("games", []):
                games.append({
                    "away": g.get("awayTeam", {}).get("placeName", {}).get("default", ""),
                    "home": g.get("homeTeam", {}).get("placeName", {}).get("default", ""),
                    "away_abbr": g.get("awayTeam", {}).get("abbrev", ""),
                    "home_abbr": g.get("homeTeam", {}).get("abbrev", ""),
                    "away_score": g.get("awayTeam", {}).get("score"),
                    "home_score": g.get("homeTeam", {}).get("score"),
                    "status": g.get("gameState", ""),
                    "detail": "",
                })
        return games
    except Exception:
        return []


def get_espn_games(sport_path, date_str=None):
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/" + sport_path + "/scoreboard"
        params = {}
        if date_str:
            params["dates"] = date_str.replace("-", "")
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        games = []
        for e in data.get("events", []):
            comp = e.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            home = {}
            away = {}
            for c in competitors:
                if c.get("homeAway") == "home":
                    home = c
                elif c.get("homeAway") == "away":
                    away = c
            st = e.get("status", {}).get("type", {})
            games.append({
                "date": e.get("date", ""),
                "away": away.get("team", {}).get("displayName", ""),
                "home": home.get("team", {}).get("displayName", ""),
                "away_abbr": away.get("team", {}).get("abbreviation", ""),
                "home_abbr": home.get("team", {}).get("abbreviation", ""),
                "away_score": away.get("score"),
                "home_score": home.get("score"),
                "status": st.get("description", ""),
                "detail": st.get("detail", ""),
            })
        return games
    except Exception:
        return []




def is_today(game):
    """True if game is within a rolling window: last ~18 hours through end of today."""
    d = game.get("date", "")
    if not d:
        return True
    try:
        game_utc = datetime.strptime(d[:16], "%Y-%m-%dT%H:%M")
        now_utc = datetime.utcnow()
        delta_hours = (now_utc - game_utc).total_seconds() / 3600.0
        # keep games that started within the last 18 hours
        # or that start within the next 24 hours
        return -24 <= delta_hours <= 18
    except Exception:
        return True


def format_games(games, league):
    if not games:
        return ""
    today = datetime.now().strftime("%B %d, %Y")
    lines = []
    lines.append("")
    lines.append(league + " GAMES TODAY (" + today + "):")
    for g in games:
        away = g.get("away", "")
        home = g.get("home", "")
        asc = g.get("away_score")
        hsc = g.get("home_score")
        status = g.get("detail") or g.get("status", "")
        if asc not in (None, "") and hsc not in (None, ""):
            lines.append("  " + away + " " + str(asc) + " at " + home + " " + str(hsc) + " - " + status)
        else:
            lines.append("  " + away + " at " + home + " - " + status)
    return "\n".join(lines)


def get_todays_games(question):
    q = question.lower()

    time_words = ["today", "tonight", "now", "current", "live", "playing",
                  "this evening", "right now", "score", "scores", "schedule",
                  "who is playing", "whos playing", "games", "game"]
    if not any(w in q for w in time_words):
        return ""

    context = ""
    sport_words = ["mlb", "baseball", "nba", "basketball", "nfl", "football",
                   "nhl", "hockey", "wnba", "soccer", "premier league", "epl"]
    wants_all = not any(s in q for s in sport_words)

    if wants_all or "mlb" in q or "baseball" in q:
        context += format_games(get_mlb_games(), "MLB")

    if (wants_all or "nba" in q or "basketball" in q) and "wnba" not in q:
        context += format_games(get_espn_games("basketball/nba"), "NBA")

    if (wants_all or "nfl" in q or ("football" in q and "soccer" not in q)):
        context += format_games(get_espn_games("football/nfl"), "NFL")

    if wants_all or "nhl" in q or "hockey" in q:
        context += format_games(get_nhl_games(), "NHL")

    if wants_all or "wnba" in q:
        context += format_games(get_espn_games("basketball/wnba"), "WNBA")

    if "soccer" in q or "premier league" in q or "epl" in q:
        context += format_games(get_espn_games("soccer/eng.1"), "PREMIER LEAGUE")

    return context
