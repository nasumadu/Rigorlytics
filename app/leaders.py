"""
Rigorlytics - league leader lookups.

"Who had the most passing yards in 2020?" names no player, so the player-based
retrieval finds nothing and the model correctly says it cannot verify. The data
is there; nothing was asking the right question of it.

This runs the ranking in SQL and hands the model the answer. Same contract as
the rest of the system: Python computes, the model narrates.
"""

import re

try:
    from app.db import get_conn
except ImportError:
    from db import get_conn


# Longest phrases first so "passing touchdowns" wins over "touchdowns".
STAT_PHRASES = [
    ("passing touchdowns", "passing.passingTouchdowns", "passing touchdowns", True),
    ("passing yards", "passing.passingYards", "passing yards", True),
    ("rushing touchdowns", "rushing.rushingTouchdowns", "rushing touchdowns", True),
    ("rushing yards", "rushing.rushingYards", "rushing yards", True),
    ("receiving touchdowns", "receiving.receivingTouchdowns", "receiving touchdowns", True),
    ("receiving yards", "receiving.receivingYards", "receiving yards", True),
    ("interceptions thrown", "passing.interceptions", "interceptions thrown", True),
    ("completion percentage", "passing.completionPct", "completion %", True),
    ("passer rating", "passing.QBRating", "passer rating", True),
    ("receptions", "receiving.receptions", "receptions", True),
    ("catches", "receiving.receptions", "receptions", True),
    ("targets", "receiving.receivingTargets", "targets", True),
    ("sacks", "defensive.sacks", "sacks", True),
    ("tackles", "defensive.totalTackles", "tackles", True),
    ("interceptions", "defensiveInterceptions.interceptions", "interceptions", True),
    ("passes defended", "defensive.passesDefended", "passes defended", True),
    ("touchdowns", "scoring.totalTouchdowns", "total touchdowns", True),
    ("epa", "advanced.passingEPA", "passing EPA", True),
    ("cpoe", "advanced.CPOE", "CPOE", True),
    # basketball
    ("points per game", "offensive.points", "points", True),
    ("points", "offensive.points", "points", True),
    ("rebounds", "general.rebounds", "rebounds", True),
    ("assists", "offensive.assists", "assists", True),
    ("blocks", "defensive.blocks", "blocks", True),
    ("steals", "defensive.steals", "steals", True),
    # soccer
    ("goals", "offensive.totalGoals", "goals", True),
    ("clean sheets", "goalKeeping.cleanSheet", "clean sheets", True),
    ("minutes", "general.minutes", "minutes", True),
    # "top scorer" means different columns in different sports, so it resolves
    # after the league is known.
    ("top scorer", "AMBIG:scorer", "scoring", True),
    ("leading scorer", "AMBIG:scorer", "scoring", True),
    ("scorer", "AMBIG:scorer", "scoring", True),
    ("scoring", "AMBIG:scorer", "scoring", True),
]

# Ambiguous phrase -> the right column per league.
AMBIGUOUS = {
    "AMBIG:scorer": {
        "NFL": ("scoring.totalPoints", "points"),
        "CFB": ("scoring.totalPoints", "points"),
        "NBA": ("offensive.points", "points"),
        "WNBA": ("offensive.points", "points"),
        "EPL": ("offensive.totalGoals", "goals"),
        "MLS": ("offensive.totalGoals", "goals"),
    },
}

LEADER_RE = re.compile(
    r"\b(most|led the|led|leads|leader|leaders|leading|tops|top|highest|"
    r"best|number one|no\.?\s*1|first in|ranked first)\b", re.I)

LEAGUE_WORDS = [
    ("nfl", "NFL"), ("national football", "NFL"),
    ("wnba", "WNBA"),
    ("nba", "NBA"),
    ("premier league", "EPL"), ("epl", "EPL"),
    ("mls", "MLS"), ("major league soccer", "MLS"),
    ("college football", "CFB"), ("cfb", "CFB"), ("ncaa", "CFB"),
]
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
POST_RE = re.compile(r"\b(playoff|playoffs|postseason|post-season)\b", re.I)


def detect(question):
    """Question -> (stat_key, label, league, year, season_type) or None."""
    if not question or not LEADER_RE.search(question):
        return None
    q = question.lower()

    stat = None
    for phrase, key, label, higher in STAT_PHRASES:
        if phrase in q:
            stat = (key, label, higher)
            break
    if not stat:
        return None

    league = None
    for word, code in LEAGUE_WORDS:
        if word in q:
            league = code
            break
    if league is None:
        # Infer from the metric family when the league is unstated.
        key = stat[0]
        if key.startswith(("passing.", "rushing.", "receiving.", "scoring.")):
            league = "NFL"
        elif key.startswith("goalKeeping.") or key == "offensive.totalGoals":
            league = "EPL"
        else:
            league = "NFL"

    if stat[0] in AMBIGUOUS:
        resolved = AMBIGUOUS[stat[0]].get(league)
        if not resolved:
            return None
        stat = (resolved[0], resolved[1], True)

    m = YEAR_RE.search(question)
    year = int(m.group(1)) if m else None
    stype = "postseason" if POST_RE.search(question) else "regular"
    return dict(stat=stat[0], label=stat[1], higher=stat[2],
                league=league, year=year, season_type=stype)


def leaders(stat, league, year, season_type="regular", limit=5):
    with get_conn() as c:
        cur = c.cursor()
        if year is None:
            cur.execute("""SELECT max(s.year) AS y FROM seasons s
                           JOIN leagues l ON l.id = s.league_id
                           WHERE l.code = %s AND s.season_type = %s""",
                        (league, season_type))
            r = cur.fetchone()
            year = dict(r)["y"] if r else None
            if year is None:
                return None, None
        cur.execute("""
            SELECT p.full_name AS name, t.name AS team,
                   (ps.stats->>%s)::float AS v
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            JOIN seasons s ON s.id = ps.season_id
            JOIN leagues l ON l.id = s.league_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE l.code = %s AND s.year = %s AND s.season_type = %s
              AND (ps.stats->>%s) IS NOT NULL
              AND (ps.stats->>%s)::float > 0
            ORDER BY 3 DESC
            LIMIT %s
        """, (stat, league, year, season_type, stat, stat, limit))
        rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""SELECT count(*) AS n FROM player_seasons ps
                       JOIN seasons s ON s.id = ps.season_id
                       JOIN leagues l ON l.id = s.league_id
                       WHERE l.code=%s AND s.year=%s AND s.season_type=%s""",
                    (league, year, season_type))
        pool = dict(cur.fetchone())["n"]
    return rows, dict(year=year, pool=pool)


def leader_context(question, limit=5):
    """Rendered block for the prompt, or '' when this is not a leader question."""
    spec = detect(question)
    if not spec:
        return ""
    rows, meta = leaders(spec["stat"], spec["league"], spec["year"],
                         spec["season_type"], limit)
    if not rows:
        return ("LEAGUE LEADERS: Rigorlytics holds no %s figures for %s %s %s, "
                "so this cannot be answered from the data."
                % (spec["label"], spec["league"], spec["year"] or "",
                   spec["season_type"]))

    L = ["LEAGUE LEADERS (ranked by Rigorlytics directly from the database - "
         "this IS the answer, state it plainly):"]
    L.append("%s %s %s season, ranked by %s, from %s player-seasons on record:"
             % (spec["league"], meta["year"], spec["season_type"], spec["label"],
                format(meta["pool"], ",")))
    for i, r in enumerate(rows, 1):
        val = r["v"]
        val = int(val) if float(val).is_integer() else round(val, 2)
        L.append("  %d. %s%s - %s %s"
                 % (i, r["name"], (" (%s)" % r["team"]) if r["team"] else "",
                    format(val, ","), spec["label"]))
    L.append("The leader is %s. This ranking covers every player-season "
             "Rigorlytics holds for that season, so it is the complete answer "
             "unless the season itself is partially loaded." % rows[0]["name"])
    return "\n".join(L)


# ---------------------------------------------------------------- card path
# Everything below serves the leaderboard CARD. It deliberately does not
# share a query with leaders(), which feeds the model: that function is
# covered by UAT category 18 and should not change shape because a UI needed
# two more columns.

# Team names whose last word is not a usable short label.
_TEAM_TAIL_STOP = {"team", "fc", "united", "city", "sc", "cf", "club"}


def _team_short(name):
    """'Houston Texans' -> 'Texans'. Falls back to the full name when the
    last word carries no meaning on its own ('Washington Football Team')."""
    if not name:
        return None
    parts = str(name).split()
    if len(parts) > 1 and parts[-1].lower() not in _TEAM_TAIL_STOP:
        return parts[-1]
    return name


def _initials(name):
    """Computed here, not in the template: a monogram fallback is data, and
    the browser should not be parsing names to draw one."""
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _display(v):
    """4823 -> '4,823';  67.8 -> '67.8';  0.582 -> '0.582'."""
    f = float(v)
    if f.is_integer():
        return format(int(f), ",")
    return format(round(f, 3 if abs(f) < 2 else 1), ",")


def leader_rows(stat, league, year, season_type="regular", limit=10):
    """leaders(), plus the identity columns a card has to render."""
    with get_conn() as c:
        cur = c.cursor()
        if year is None:
            cur.execute("""SELECT max(s.year) AS y FROM seasons s
                           JOIN leagues l ON l.id = s.league_id
                           WHERE l.code = %s AND s.season_type = %s""",
                        (league, season_type))
            r = cur.fetchone()
            year = dict(r)["y"] if r else None
            if year is None:
                return None, None

        cur.execute("""
            SELECT p.id AS player_id, p.full_name AS name, p.position,
                   p.headshot_url, t.name AS team,
                   (ps.stats->>%s)::float AS v
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            JOIN seasons s ON s.id = ps.season_id
            JOIN leagues l ON l.id = s.league_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE l.code = %s AND s.year = %s AND s.season_type = %s
              AND (ps.stats->>%s) IS NOT NULL
              AND (ps.stats->>%s)::float > 0
            ORDER BY 6 DESC
            LIMIT %s
        """, (stat, league, year, season_type, stat, stat, limit))
        rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""SELECT count(*) AS n FROM player_seasons ps
                       JOIN seasons s ON s.id = ps.season_id
                       JOIN leagues l ON l.id = s.league_id
                       WHERE l.code=%s AND s.year=%s AND s.season_type=%s""",
                    (league, year, season_type))
        pool = dict(cur.fetchone())["n"]
    return rows, dict(year=year, pool=pool)


def build_leaderboard(question, limit=10):
    """Question -> leaderboard card payload, or None when it is not one.

    Sibling of compare.build_comparison(): same contract, same shape of
    return, so the front end switches on payload["type"] and nothing else.
    """
    spec = detect(question)
    if not spec:
        return None

    rows, meta = leader_rows(spec["stat"], spec["league"], spec["year"],
                             spec["season_type"], limit)
    if not rows:
        return None

    out = []
    prev_v = None
    prev_rank = 0
    for i, r in enumerate(rows, 1):
        # Equal values share a rank. Enumerating positions would print a
        # 1 and a 2 for two identical figures, which is a wrong answer
        # dressed up as a precise one.
        if prev_v is not None and float(r["v"]) == prev_v:
            rank = prev_rank
        else:
            rank = i
        prev_v, prev_rank = float(r["v"]), rank

        out.append({
            "rank": rank,
            "player_id": r["player_id"],
            "name": r["name"],
            "position": r.get("position"),
            "team": r.get("team"),
            "team_short": _team_short(r.get("team")),
            "value": float(r["v"]),
            "display": _display(r["v"]),
            "headshot": r.get("headshot_url"),
            "initials": _initials(r["name"]),
        })

    season_label = "%s%s" % (meta["year"],
                             " playoffs" if spec["season_type"] == "postseason"
                             else "")
    return {
        "type": "leaderboard",
        "title": "%s %s %s" % (season_label, spec["league"], spec["label"]),
        "stat_label": spec["label"],
        "league": spec["league"],
        "year": meta["year"],
        "season_type": spec["season_type"],
        # Provenance on the card itself, in the same spirit as the line
        # leader_context() gives the model: the reader can see what the
        # ranking was computed over rather than taking it on faith.
        "pool": meta["pool"],
        "rows": out,
    }
