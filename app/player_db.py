"""Database-backed player lookup. Falls back to live ESPN when a player is missing."""

import json
from app.db import query, get_conn

# Which JSONB keys to surface per league, and how to label them
FIELDS = {
    "NBA": [
        ("general.gamesPlayed", "Games"),
        ("offensive.avgPoints", "PPG"),
        ("general.avgRebounds", "RPG"),
        ("offensive.avgAssists", "APG"),
        ("defensive.avgSteals", "SPG"),
        ("defensive.avgBlocks", "BPG"),
        ("offensive.avgMinutes", "MPG"),
        ("offensive.fieldGoalPct", "FG%"),
        ("offensive.threePointFieldGoalPct", "3P%"),
        ("offensive.freeThrowPct", "FT%"),
        ("offensive.effectiveFGPct", "eFG%"),
        ("offensive.trueShootingPct", "TS%"),
        ("general.PER", "PER"),
    ],
    "WNBA": [
        ("general.gamesPlayed", "Games"),
        ("offensive.avgPoints", "PPG"),
        ("general.avgRebounds", "RPG"),
        ("offensive.avgAssists", "APG"),
        ("offensive.fieldGoalPct", "FG%"),
        ("offensive.threePointFieldGoalPct", "3P%"),
        ("offensive.trueShootingPct", "TS%"),
    ],
    "NFL": [
        ("general.gamesPlayed", "Games"),
        ("passing.passingYards", "Pass Yds"),
        ("passing.passingTouchdowns", "Pass TD"),
        ("passing.interceptions", "INT"),
        ("passing.completionPct", "Comp%"),
        ("passing.QBRating", "Rating"),
        ("rushing.rushingYards", "Rush Yds"),
        ("rushing.rushingTouchdowns", "Rush TD"),
        ("rushing.yardsPerRushAttempt", "Y/C"),
        ("receiving.receptions", "Rec"),
        ("receiving.receivingYards", "Rec Yds"),
        ("receiving.receivingTouchdowns", "Rec TD"),
        ("receiving.receivingTargets", "Targets"),
        ("defensive.totalTackles", "Tackles"),
        ("defensive.sacks", "Sacks"),
    ],
    "MLB": [
        ("general.gamesPlayed", "Games"),
        ("batting.avg", "AVG"),
        ("batting.homeRuns", "HR"),
        ("batting.RBIs", "RBI"),
        ("batting.runs", "Runs"),
        ("batting.hits", "Hits"),
        ("batting.OPS", "OPS"),
        ("batting.onBasePct", "OBP"),
        ("batting.slugAvg", "SLG"),
        ("pitching.ERA", "ERA"),
        ("pitching.wins", "W"),
        ("pitching.strikeouts", "K"),
        ("pitching.WHIP", "WHIP"),
    ],
    "NHL": [
        ("general.gamesPlayed", "Games"),
        ("offensive.goals", "Goals"),
        ("offensive.assists", "Assists"),
        ("offensive.points", "Points"),
        ("offensive.plusMinus", "+/-"),
        ("offensive.shootingPct", "Shot%"),
        ("goalie.savePct", "SV%"),
        ("goalie.goalsAgainstAverage", "GAA"),
    ],
}

CAREER_KEYS = {
    "NBA": ["offensive.avgPoints", "general.avgRebounds", "offensive.avgAssists",
            "offensive.fieldGoalPct", "offensive.threePointFieldGoalPct",
            "offensive.trueShootingPct", "general.PER"],
    "WNBA": ["offensive.avgPoints", "general.avgRebounds", "offensive.avgAssists",
             "offensive.trueShootingPct"],
    "NFL": ["passing.passingYards", "passing.passingTouchdowns", "rushing.rushingYards",
            "receiving.receptions", "receiving.receivingYards"],
    "MLB": ["batting.avg", "batting.homeRuns", "batting.OPS", "pitching.ERA"],
    "NHL": ["offensive.goals", "offensive.assists", "offensive.points"],
}

LABELS = {k: dict(v) for k, v in FIELDS.items()}


def find_players(name):
    """Find matching players by name. Exact match first, then partial."""
    rows = query("""
        SELECT p.id, p.full_name, p.external_id, p.position, l.code AS league
        FROM players p JOIN leagues l ON l.id = p.league_id
        WHERE lower(p.full_name) = lower(%s)
        LIMIT 5
    """, (name,))
    if rows:
        return rows

    return query("""
        SELECT p.id, p.full_name, p.external_id, p.position, l.code AS league
        FROM players p JOIN leagues l ON l.id = p.league_id
        WHERE p.full_name ILIKE %s
        ORDER BY length(p.full_name)
        LIMIT 5
    """, (name + "%",))


def get_seasons(player_id, limit=14):
    return query("""
        SELECT s.year, ps.games_played, ps.stats, ps.per, ps.true_shooting
        FROM player_seasons ps JOIN seasons s ON s.id = ps.season_id
        WHERE ps.player_id = %s
        ORDER BY s.year DESC
        LIMIT %s
    """, (player_id, limit))


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except Exception:
        return None


def format_player(player):
    """Build a context block for one player from the database."""
    league = player["league"]
    seasons = get_seasons(player["id"])
    if not seasons:
        return ""

    fields = FIELDS.get(league, [])
    labels = LABELS.get(league, {})

    block = "\n" + league + " PLAYER: " + player["full_name"] + "\n"
    if player.get("position"):
        block += "Position: " + str(player["position"]) + "\n"
    block += "Seasons of data: " + str(len(seasons)) + "\n"

    # career averages
    ck = CAREER_KEYS.get(league, [])
    car = []
    for key in ck:
        vals = []
        for s in seasons:
            stats = s["stats"] or {}
            v = _num(stats.get(key))
            if v is not None:
                vals.append(v)
        if vals:
            car.append("    " + labels.get(key, key) + ": " + ("%.1f" % (sum(vals) / len(vals))))
    if car:
        block += "\n  CAREER AVERAGE (across %d seasons):\n" % len(seasons)
        block += "\n".join(car) + "\n"

    block += "\n  SEASON BY SEASON:\n"
    for s in seasons:
        stats = s["stats"] or {}
        lines = []
        for key, label in fields:
            v = stats.get(key)
            if v in (None, "", 0):
                continue
            if isinstance(v, float):
                v = round(v, 2)
            lines.append("    " + label + ": " + str(v))
        if lines:
            block += "\n  " + str(s["year"]) + ":\n" + "\n".join(lines) + "\n"

    return block


def lookup_from_db(name):
    """Return a formatted block for a name, or empty string if not found."""
    matches = find_players(name)
    for m in matches:
        block = format_player(m)
        if block:
            return block
    return ""
