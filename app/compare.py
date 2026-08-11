"""Build structured side-by-side player comparisons from the database."""

from app.db import query
from app.player_db import find_players, get_seasons, _num

# Stat rows per position group. Each entry: (jsonb key, label, per_season, higher_is_better)
ROWS = {
    "QB": [
        ("passing.passingYards", "Pass yds / season", True, True),
        ("passing.passingTouchdowns", "Pass TD / season", True, True),
        ("passing.interceptions", "INT / season", True, False),
        ("passing.completionPct", "Completion %", False, True),
        ("passing.QBRating", "Passer rating", False, True),
        ("rushing.rushingYards", "Rush yds / season", True, True),
        ("rushing.rushingTouchdowns", "Rush TD / season", True, True),
        ("general.gamesPlayed", "Games / season", False, True),
    ],
    "RB": [
        ("rushing.rushingYards", "Rush yds / season", True, True),
        ("rushing.rushingTouchdowns", "Rush TD / season", True, True),
        ("rushing.yardsPerRushAttempt", "Yards per carry", False, True),
        ("receiving.receptions", "Rec / season", True, True),
        ("receiving.receivingYards", "Rec yds / season", True, True),
        ("general.gamesPlayed", "Games / season", False, True),
    ],
    "WR": [
        ("receiving.receptions", "Rec / season", True, True),
        ("receiving.receivingYards", "Rec yds / season", True, True),
        ("receiving.receivingTouchdowns", "Rec TD / season", True, True),
        ("receiving.yardsPerReception", "Yards per catch", False, True),
        ("receiving.receivingTargets", "Targets / season", True, True),
        ("general.gamesPlayed", "Games / season", False, True),
    ],
    "NBA": [
        ("offensive.avgPoints", "Points per game", False, True),
        ("general.avgRebounds", "Rebounds per game", False, True),
        ("offensive.avgAssists", "Assists per game", False, True),
        ("offensive.fieldGoalPct", "Field goal %", False, True),
        ("offensive.threePointFieldGoalPct", "Three point %", False, True),
        ("offensive.trueShootingPct", "True shooting %", False, True),
        ("general.PER", "PER", False, True),
        ("general.gamesPlayed", "Games / season", False, True),
    ],
    "MLB": [
        ("batting.avg", "Batting average", False, True),
        ("batting.homeRuns", "HR / season", True, True),
        ("batting.RBIs", "RBI / season", True, True),
        ("batting.OPS", "OPS", False, True),
        ("batting.onBasePct", "On base %", False, True),
        ("general.gamesPlayed", "Games / season", False, True),
    ],
    "NHL": [
        ("offensive.goals", "Goals / season", True, True),
        ("offensive.assists", "Assists / season", True, True),
        ("offensive.points", "Points / season", True, True),
        ("offensive.plusMinus", "Plus minus", False, True),
        ("general.gamesPlayed", "Games / season", False, True),
    ],
}

WR_LIKE = {"WR", "TE"}
RB_LIKE = {"RB", "FB", "HB"}


def position_group(league, position):
    """Map a league and position to a stat row set."""
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
    """Resolve a name to a player with season data, or None."""
    for m in find_players(name):
        seasons = get_seasons(m["id"], limit=25)
        if seasons:
            return {
                "id": m["id"],
                "name": m["full_name"],
                "league": m["league"],
                "position": m.get("position"),
                "seasons": seasons,
            }
    return None


def averages(seasons, rows):
    """Compute per-season averages for each stat row."""
    out = {}
    n = len(seasons)
    for key, label, per_season, higher in rows:
        vals = []
        for s in seasons:
            v = _num((s["stats"] or {}).get(key))
            if v is not None:
                vals.append(v)
        if not vals:
            continue
        out[key] = sum(vals) / len(vals)
    return out


def build_comparison(name_a, name_b):
    """Return a comparison payload, or None if the pair cannot be compared."""
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
    avg_a = averages(a["seasons"], rows)
    avg_b = averages(b["seasons"], rows)

    out_rows = []
    wins_a = 0
    wins_b = 0
    for key, label, per_season, higher in rows:
        if key not in avg_a or key not in avg_b:
            continue
        va = avg_a[key]
        vb = avg_b[key]
        if higher:
            winner = "a" if va > vb else ("b" if vb > va else None)
        else:
            winner = "a" if va < vb else ("b" if vb < va else None)
        if winner == "a":
            wins_a += 1
        elif winner == "b":
            wins_b += 1
        out_rows.append({
            "label": label,
            "a": round(va, 1),
            "b": round(vb, 1),
            "winner": winner,
        })

    if len(out_rows) < 3:
        return None

    return {
        "type": "comparison",
        "league": a["league"],
        "position_group": ga,
        "a": {"name": a["name"], "position": a["position"], "seasons": len(a["seasons"])},
        "b": {"name": b["name"], "position": b["position"], "seasons": len(b["seasons"])},
        "rows": out_rows,
        "wins": {"a": wins_a, "b": wins_b},
    }
