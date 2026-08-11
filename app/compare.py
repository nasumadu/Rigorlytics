"""Build structured side-by-side player comparisons from the database."""

from app.db import query
from app.player_db import find_players, get_seasons, _num

# (jsonb key, label, mode, higher_is_better)
# mode: "sum" = career total, "avg" = per-season average, "rate" = averaged rate
ROWS = {
    "QB": [
        ("__section__", "Overall", None, None),
        ("general.gamesPlayed", "Games", "sum", True),
        ("passing.QBRating", "Passer rating", "rate", True),
        ("passing.QBR", "ESPN QBR", "rate", True),
        ("__section__", "Passing", None, None),
        ("passing.completionPct", "Completion %", "rate", True),
        ("passing.passingYards", "Pass yards", "sum", True),
        ("passing.yardsPerPassAttempt", "Yards per attempt", "rate", True),
        ("passing.passingYardsPerGame", "Pass yards per game", "rate", True),
        ("passing.passingTouchdowns", "Pass TD", "sum", True),
        ("passing.interceptions", "Interceptions", "sum", False),
        ("__section__", "Rushing", None, None),
        ("rushing.rushingAttempts", "Rush attempts", "sum", True),
        ("rushing.rushingYards", "Rush yards", "sum", True),
        ("rushing.yardsPerRushAttempt", "Yards per carry", "rate", True),
        ("rushing.rushingTouchdowns", "Rush TD", "sum", True),
    ],
    "RB": [
        ("__section__", "Overall", None, None),
        ("general.gamesPlayed", "Games", "sum", True),
        ("__section__", "Rushing", None, None),
        ("rushing.rushingAttempts", "Rush attempts", "sum", True),
        ("rushing.rushingYards", "Rush yards", "sum", True),
        ("rushing.yardsPerRushAttempt", "Yards per carry", "rate", True),
        ("rushing.rushingYardsPerGame", "Rush yards per game", "rate", True),
        ("rushing.rushingTouchdowns", "Rush TD", "sum", True),
        ("__section__", "Receiving", None, None),
        ("receiving.receptions", "Receptions", "sum", True),
        ("receiving.receivingYards", "Rec yards", "sum", True),
        ("receiving.receivingTouchdowns", "Rec TD", "sum", True),
    ],
    "WR": [
        ("__section__", "Overall", None, None),
        ("general.gamesPlayed", "Games", "sum", True),
        ("__section__", "Receiving", None, None),
        ("receiving.receptions", "Receptions", "sum", True),
        ("receiving.receivingTargets", "Targets", "sum", True),
        ("receiving.receivingYards", "Rec yards", "sum", True),
        ("receiving.yardsPerReception", "Yards per catch", "rate", True),
        ("receiving.receivingYardsPerGame", "Rec yards per game", "rate", True),
        ("receiving.receivingTouchdowns", "Rec TD", "sum", True),
        ("receiving.receivingFirstDowns", "First downs", "sum", True),
    ],
    "NBA": [
        ("__section__", "Overall", None, None),
        ("general.gamesPlayed", "Games", "sum", True),
        ("general.PER", "PER", "rate", True),
        ("__section__", "Scoring", None, None),
        ("offensive.avgPoints", "Points per game", "rate", True),
        ("offensive.fieldGoalPct", "Field goal %", "rate", True),
        ("offensive.threePointFieldGoalPct", "Three point %", "rate", True),
        ("offensive.freeThrowPct", "Free throw %", "rate", True),
        ("offensive.trueShootingPct", "True shooting %", "rate", True),
        ("__section__", "All around", None, None),
        ("general.avgRebounds", "Rebounds per game", "rate", True),
        ("offensive.avgAssists", "Assists per game", "rate", True),
        ("defensive.avgSteals", "Steals per game", "rate", True),
        ("defensive.avgBlocks", "Blocks per game", "rate", True),
    ],
    "MLB": [
        ("__section__", "Overall", None, None),
        ("general.gamesPlayed", "Games", "sum", True),
        ("__section__", "Batting", None, None),
        ("batting.avg", "Batting average", "rate", True),
        ("batting.hits", "Hits", "sum", True),
        ("batting.homeRuns", "Home runs", "sum", True),
        ("batting.RBIs", "RBI", "sum", True),
        ("batting.runs", "Runs", "sum", True),
        ("batting.onBasePct", "On base %", "rate", True),
        ("batting.slugAvg", "Slugging", "rate", True),
        ("batting.OPS", "OPS", "rate", True),
    ],
    "NHL": [
        ("__section__", "Overall", None, None),
        ("general.gamesPlayed", "Games", "sum", True),
        ("__section__", "Scoring", None, None),
        ("offensive.goals", "Goals", "sum", True),
        ("offensive.assists", "Assists", "sum", True),
        ("offensive.points", "Points", "sum", True),
        ("offensive.plusMinus", "Plus minus", "sum", True),
        ("offensive.shootingPct", "Shooting %", "rate", True),
    ],
}

WR_LIKE = {"WR", "TE"}
RB_LIKE = {"RB", "FB", "HB"}


def position_group(league, position):
    if league in ("NBA", "WNBA"):
        return "NBA"
    if league == "MLB":
        return "MLB"
    if league == "NHL":
        return "NHL"
    p = (position or "").upper()
    if p == "QB":
        return "QB"
    if p in RB_LIKE:
        return "RB"
    if p in WR_LIKE:
        return "WR"
    return None


def player_profile(name):
    for m in find_players(name):
        seasons = get_seasons(m["id"], limit=30)
        if seasons:
            extra = query("""SELECT headshot_url, jersey, height_inches, weight_lbs
                             FROM players WHERE id = %s""", (m["id"],))
            e = extra[0] if extra else {}
            return {
                "id": m["id"],
                "name": m["full_name"],
                "league": m["league"],
                "position": m.get("position"),
                "seasons": seasons,
                "headshot": e.get("headshot_url"),
                "jersey": e.get("jersey"),
            }
    return None


def aggregate(seasons, key, mode):
    vals = []
    for s in seasons:
        v = _num((s["stats"] or {}).get(key))
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    if mode == "sum":
        return sum(vals)
    return sum(vals) / len(vals)


def build_comparison(name_a, name_b):
    a = player_profile(name_a)
    b = player_profile(name_b)
    if not a or not b:
        return None
    if a["league"] != b["league"]:
        return None

    ga = position_group(a["league"], a["position"])
    gb = position_group(b["league"], b["position"])
    if not ga or ga != gb:
        return None

    rows = ROWS[ga]
    out = []
    wins_a = 0
    wins_b = 0
    pending_section = None

    for key, label, mode, higher in rows:
        if key == "__section__":
            pending_section = label
            continue

        va = aggregate(a["seasons"], key, mode)
        vb = aggregate(b["seasons"], key, mode)
        if va is None or vb is None:
            continue

        decimals = 0 if mode == "sum" else (3 if abs(va) < 2 else 1)
        ra = round(va, decimals)
        rb = round(vb, decimals)

        if ra == rb:
            winner = None
        elif higher:
            winner = "a" if ra > rb else "b"
        else:
            winner = "a" if ra < rb else "b"

        if winner == "a":
            wins_a += 1
        elif winner == "b":
            wins_b += 1

        if pending_section:
            out.append({"section": pending_section})
            pending_section = None

        out.append({
            "label": label,
            "a": ra,
            "b": rb,
            "winner": winner,
        })

    stat_rows = [r for r in out if "label" in r]
    if len(stat_rows) < 4:
        return None

    return {
        "type": "comparison",
        "league": a["league"],
        "position_group": ga,
        "a": {"name": a["name"], "position": a["position"], "seasons": len(a["seasons"]),
              "headshot": a["headshot"], "jersey": a["jersey"]},
        "b": {"name": b["name"], "position": b["position"], "seasons": len(b["seasons"]),
              "headshot": b["headshot"], "jersey": b["jersey"]},
        "rows": out,
        "wins": {"a": wins_a, "b": wins_b},
    }
