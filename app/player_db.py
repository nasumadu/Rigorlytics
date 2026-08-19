"""Database-backed player lookup. Falls back to live ESPN when a player is missing."""

import json
from app.db import query, get_conn
from app.aliases import resolve_alias

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
    name = resolve_alias(name)
    rows = query("""
        SELECT p.id, p.full_name, p.external_id, p.position, l.code AS league,
               (SELECT count(*) FROM player_seasons ps WHERE ps.player_id = p.id) AS n
        FROM players p JOIN leagues l ON l.id = p.league_id
        WHERE lower(p.full_name) = lower(%s)
        ORDER BY n DESC
        LIMIT 5
    """, (name,))
    if rows:
        return rows

    return query("""
        SELECT p.id, p.full_name, p.external_id, p.position, l.code AS league,
               (SELECT count(*) FROM player_seasons ps WHERE ps.player_id = p.id) AS n
        FROM players p JOIN leagues l ON l.id = p.league_id
        WHERE p.full_name ILIKE %s
        ORDER BY n DESC, length(p.full_name)
        LIMIT 5
    """, (name + "%",))


def get_seasons(player_id, season_type="regular", limit=30):
    # One season type per call. Pooling them counted 2021 twice for any player
    # who made the playoffs, and averaged a three-game run into a 17-game year.
    return query("""
        SELECT s.year, s.season_type, ps.games_played, ps.stats, ps.per,
               ps.true_shooting
        FROM player_seasons ps JOIN seasons s ON s.id = ps.season_id
        WHERE ps.player_id = %s AND s.season_type = %s
        ORDER BY s.year DESC
        LIMIT %s
    """, (player_id, season_type, limit))


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except Exception:
        return None


def format_player(player):
    # Regular and postseason are reported as two separate records. They are
    # different sample sizes answering different questions, and the model has
    # no way to tell them apart if they arrive in one undifferentiated list.
    league = player["league"]
    seasons = get_seasons(player["id"], "regular")
    post = get_seasons(player["id"], "postseason")
    if not seasons and not post:
        return ""

    fields = FIELDS.get(league, [])
    labels = LABELS.get(league, {})

    def rows_for(s):
        stats = s["stats"] or {}
        lines = []
        for key, label in fields:
            v = stats.get(key)
            if v in (None, "", 0):
                continue
            if isinstance(v, float):
                v = round(v, 2)
            lines.append("    " + label + ": " + str(v))
        return lines

    block = "\n" + league + " PLAYER: " + player["full_name"] + "\n"
    if player.get("position"):
        block += "Position: " + str(player["position"]) + "\n"
    block += ("Regular seasons held: %d (%s)\n"
              % (len(seasons),
                 ", ".join(str(s["year"]) for s in seasons) if seasons else "none"))
    if post:
        block += ("Postseason rows held: %d (%s). These are SEPARATE from the "
                  "seasons above, are not counted in any total or average "
                  "below, and must never be described as extra seasons.\n"
                  % (len(post), ", ".join(str(s["year"]) for s in post)))

    ck = CAREER_KEYS.get(league, [])
    car = []
    for key in ck:
        vals = []
        for s in seasons:
            v = _num((s["stats"] or {}).get(key))
            if v is not None:
                vals.append(v)
        # A receiver stores passing.passingYards as 0.0 in every season he never
        # threw. Averaging those gives Ja'Marr Chase a career passing figure of
        # -1.4 - arithmetically correct, and an invitation to narrate something
        # absurd. A metric earns a career line only if it is live in most of the
        # seasons held.
        live = [v for v in vals if v]
        if vals and len(live) * 2 >= len(vals):
            # Each metric carries its own denominator. Labelling every one with
            # the full season count is how a receiver reports a passing average.
            car.append("    %s: %.1f  (mean of the %d season%s carrying it)"
                       % (labels.get(key, key), sum(vals) / len(vals),
                          len(vals), "" if len(vals) == 1 else "s"))
    if car:
        block += "\n  REGULAR-SEASON PER-SEASON AVERAGE (regular season only):\n"
        block += "\n".join(car) + "\n"

    if seasons:
        block += "\n  REGULAR SEASON, YEAR BY YEAR:\n"
        for s in seasons:
            lines = rows_for(s)
            if lines:
                block += "\n  " + str(s["year"]) + ":\n" + "\n".join(lines) + "\n"

    if post:
        block += "\n  POSTSEASON, YEAR BY YEAR (separate record, small samples):\n"
        for s in post:
            lines = rows_for(s)
            if lines:
                block += ("\n  " + str(s["year"]) + " playoffs:\n"
                          + "\n".join(lines) + "\n")

    return block


def lookup_from_db(name):
    """Return a formatted block for a name, or empty string if not found."""
    matches = find_players(name)
    for m in matches:
        block = format_player(m)
        if block:
            return block
    return ""
