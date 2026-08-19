#!/usr/bin/env python3
"""
Rigorlytics - valuation engine.

"Narrate, don't compute." Everything a GM, agent or player would want asserted
about a player is computed HERE, in Python, against the database. The language
model receives this object and writes prose about it. It never does arithmetic,
never estimates a salary, and never invents a comparable.

Every number carries provenance and a claim tier:

    fact       read directly from a row we ingested        (source + as_of)
    derived    computed from facts by code in this file    (percentile, per-90)
    inference  a projection with stated assumptions        (value band)

Leagues without licensed salary data never produce a money claim. EPL has no
published wages anywhere, so its money axis is market value and transfer fee.

    from app.valuation import analyze
    obj = analyze("Bukayo Saka")

CLI:
    python -m app.valuation --player "Bukayo Saka"
    python -m app.valuation --player "Alex Morgan" --league MLS --json
"""

import os, sys, json, math, argparse, datetime, unicodedata, re

try:
    from app.db import get_conn
except ImportError:  # running as a script from repo root
    sys.path.insert(0, os.getcwd())
    from app.db import get_conn


# ------------------------------------------------------------------ config

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Minimum workload before a player is allowed into a cohort as a peer.
MIN_WORKLOAD = {"soccer": 450.0, "basketball": 200.0, "football": 4.0}

# Comparables must be age-similar or the money axis is meaningless.
AGE_BANDS = (2.5, 4.0, 6.0)
MIN_COMP_POOL = 12

# ("stat key", "label", mode, higher_is_better)
#   total    - raw season total
#   rate     - already a percentage/ratio, used as-is
#   per90    - normalised per 90 minutes (soccer)
#   pergame  - normalised per game played
METRICS = {
    "soccer": {
        "_all": [
            ("general.appearances", "Appearances", "total", True),
            ("general.starts", "Starts", "total", True),
            ("general.minutes", "Minutes", "total", True),
        ],
        "F": [
            ("offensive.totalGoals", "Goals", "per90", True),
            ("offensive.goalAssists", "Assists", "per90", True),
            ("offensive.headedGoals", "Headed goals", "total", True),
            ("general.touches", "Touches", "per90", True),
            ("general.passPct", "Pass accuracy", "rate", True),
        ],
        "M": [
            ("offensive.goalAssists", "Assists", "per90", True),
            ("offensive.totalGoals", "Goals", "per90", True),
            ("general.passPct", "Pass accuracy", "rate", True),
            ("offensive.accurateThroughBalls", "Through balls", "per90", True),
            ("defensive.totalTackles", "Tackles", "per90", True),
            ("general.touches", "Touches", "per90", True),
        ],
        "D": [
            ("defensive.totalTackles", "Tackles", "per90", True),
            ("defensive.interceptions", "Interceptions", "per90", True),
            ("defensive.totalClearance", "Clearances", "per90", True),
            ("general.passPct", "Pass accuracy", "rate", True),
            ("general.foulsCommitted", "Fouls committed", "per90", False),
        ],
        "G": [
            ("goalKeeping.cleanSheet", "Clean sheets", "total", True),
            ("goalKeeping.goalsConceded", "Goals conceded", "per90", False),
            ("goalKeeping.crossesCaught", "Crosses caught", "per90", True),
            ("goalKeeping.penaltyKickSavePct", "Penalty save %", "rate", True),
        ],
    },
    "basketball": {
        "_all": [
            ("general.gamesPlayed", "Games", "total", True),
            ("general.minutes", "Minutes", "total", True),
            ("offensive.points", "Points", "pergame", True),
            ("general.rebounds", "Rebounds", "pergame", True),
            ("defensive.steals", "Steals", "pergame", True),
            ("defensive.blocks", "Blocks", "pergame", True),
            ("general.VORP", "VORP", "total", True),
            ("general.PER", "PER", "rate", True),
        ],
        "G": [("offensive.assists", "Assists", "pergame", True)],
        "F": [("offensive.offensiveReboundPct", "Off. reb %", "rate", True)],
        "C": [("defensive.blocks", "Blocks", "pergame", True)],
    },
    "football": {
        "_all": [("general.gamesPlayed", "Games", "total", True)],
        "QB": [
            ("passing.passingYards", "Passing yards", "total", True),
            ("passing.passingTouchdowns", "Passing TDs", "total", True),
            ("passing.interceptions", "Interceptions", "total", False),
            ("passing.QBRating", "Passer rating", "rate", True),
            # nflverse supplies these from 1999 on. EPA measures value added per
            # play and CPOE isolates accuracy from scheme, so both survive the
            # era comparisons that raw yardage totals fail.
            ("advanced.passingEPA", "Passing EPA", "total", True),
            ("advanced.CPOE", "CPOE", "rate", True),
            ("passing.completionPct", "Completion %", "rate", True),
        ],
        "RB": [
            ("rushing.rushingYards", "Rushing yards", "total", True),
            ("rushing.rushingTouchdowns", "Rushing TDs", "total", True),
            ("rushing.yardsPerRushAttempt", "Yards per carry", "rate", True),
            ("receiving.receptions", "Receptions", "total", True),
        ],
        "WR": [
            ("receiving.receivingYards", "Receiving yards", "total", True),
            ("receiving.receptions", "Receptions", "total", True),
            ("receiving.receivingTouchdowns", "Receiving TDs", "total", True),
            ("receiving.yardsPerReception", "Yards per catch", "rate", True),
        ],
        "TE": [
            ("receiving.receivingYards", "Receiving yards", "total", True),
            ("receiving.receptions", "Receptions", "total", True),
            ("receiving.receivingTouchdowns", "Receiving TDs", "total", True),
        ],
        "DL": [
            ("defensive.sacks", "Sacks", "total", True),
            ("defensive.totalTackles", "Tackles", "total", True),
            ("defensive.tacklesForLoss", "TFL", "total", True),
        ],
        "LB": [
            ("defensive.totalTackles", "Tackles", "total", True),
            ("defensive.sacks", "Sacks", "total", True),
            ("defensive.passesDefended", "Passes defended", "total", True),
        ],
        "DB": [
            ("defensive.totalTackles", "Tackles", "total", True),
            ("defensive.passesDefended", "Passes defended", "total", True),
            ("defensiveInterceptions.interceptions", "Interceptions", "total", True),
        ],
        "OL": [("general.gamesStarted", "Starts", "total", True)],
        "ST": [("scoring.totalPoints", "Points", "total", True)],
    },
}

POS_GROUP = {
    "football": {
        "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
        "C": "OL", "G": "OL", "OG": "OL", "OT": "OL", "OL": "OL", "T": "OL",
        "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL",
        "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
        "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "DB": "DB",
        "PK": "ST", "P": "ST", "LS": "ST", "KR": "ST", "K": "ST",
    },
    "basketball": {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F",
                   "F": "F", "C": "C"},
    "soccer": {"G": "G", "GK": "G", "D": "D", "M": "M", "F": "F"},
}

# Which money axis each league is allowed to speak in.
MONEY_AXIS = {
    "MLS":  ("salary", "MLSPA disclosure"),
    "NFL":  ("salary", "contract data"),
    "NBA":  ("salary", "contract data"),
    "EPL":  ("market_value", "Transfermarkt market value"),
    "WNBA": (None, None),
    "CFB":  (None, None),
}


# ------------------------------------------------------------------ helpers

def norm_name(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("-", " ").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(p for p in s.split() if p and p not in SUFFIXES)


def pct_rank(values, x):
    """Share of the cohort at or below x, 0..100. Ties counted at half."""
    if not values:
        return None
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return round(100.0 * (below + 0.5 * equal) / len(values), 1)


def median(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def quantile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def age_from(birth_date, today=None):
    if not birth_date:
        return None
    today = today or datetime.date.today()
    return round((today - birth_date).days / 365.25, 1)


def workload(stats, sport):
    if sport == "soccer":
        return stats.get("general.minutes") or 0.0
    if sport == "basketball":
        return stats.get("general.minutes") or 0.0
    return stats.get("general.gamesPlayed") or 0.0


def metric_value(stats, key, mode, sport):
    """Raw stat -> the value we actually rank on."""
    v = stats.get(key)
    if v is None:
        return None
    if mode == "rate" or mode == "total":
        return float(v)
    if mode == "per90":
        mins = stats.get("general.minutes") or 0.0
        return (float(v) * 90.0 / mins) if mins >= 90 else None
    if mode == "pergame":
        gp = stats.get("general.gamesPlayed") or 0.0
        return (float(v) / gp) if gp >= 1 else None
    return float(v)


def metric_specs(sport, group):
    specs = list(METRICS.get(sport, {}).get("_all", []))
    seen = {s[0] for s in specs}
    for spec in METRICS.get(sport, {}).get(group, []):
        if spec[0] not in seen:
            specs.append(spec)
            seen.add(spec[0])
    return specs


# ------------------------------------------------------------------ loading

def find_player(cur, name, league=None):
    """Resolve a name to player rows.

    Narrowed in SQL on the surname first so a chat request does not scan the
    whole players table; falls back to a full scan only when the narrow pass
    finds nothing, which is what catches accented spellings the LIKE misses.
    """
    n = norm_name(name)
    if not n:
        return []
    base = """SELECT p.id, p.full_name, p.position, p.birth_date, p.headshot_url,
                     l.code AS league, l.sport
              FROM players p JOIN leagues l ON l.id = p.league_id
              WHERE p.full_name IS NOT NULL"""
    scope, args = "", []
    if league:
        scope = " AND l.code = %s"
        args = [league.upper()]

    def sift(rows):
        exact, loose = [], []
        for r in rows:
            r = dict(r)
            rn = norm_name(r["full_name"])
            if rn == n:
                exact.append(r)
            elif n in rn:
                loose.append(r)
        return exact or loose

    cur.execute(base + scope + " AND p.full_name ILIKE %s",
                args + ["%" + n.split()[-1] + "%"])
    hit = sift(cur.fetchall())
    if hit:
        return hit
    cur.execute(base + scope, args)
    return sift(cur.fetchall())


def cohort_rows(cur, league, sport, group, season_year=None):
    """Every player in the league whose position maps to the same group."""
    cur.execute("""
        SELECT p.id, p.full_name, p.position, p.birth_date,
               ps.stats, ps.games_played, ps.source, s.year, t.name AS team_name
        FROM player_seasons ps
        JOIN players p ON p.id = ps.player_id
        JOIN leagues l ON l.id = p.league_id
        JOIN seasons s ON s.id = ps.season_id
        LEFT JOIN teams t ON t.id = ps.team_id
        WHERE l.code = %s AND p.position IS NOT NULL
          AND s.season_type = 'regular'
    """, (league,))
    out = []
    gmap = POS_GROUP.get(sport, {})
    for r in cur.fetchall():
        r = dict(r)
        if gmap.get((r["position"] or "").upper()) != group:
            continue
        st = r["stats"]
        if isinstance(st, str):
            try:
                st = json.loads(st)
            except ValueError:
                continue
        if not st:
            continue
        r["stats"] = st
        out.append(r)
    return out


def postseason_for(cur, league, player_ids):
    """Most recent playoff row per player, keyed by players.id."""
    if not player_ids:
        return {}
    cur.execute("""
        SELECT ps.player_id, ps.stats, ps.games_played, s.year
        FROM player_seasons ps
        JOIN seasons s ON s.id = ps.season_id
        JOIN players p ON p.id = ps.player_id
        JOIN leagues l ON l.id = p.league_id
        WHERE l.code = %s AND s.season_type = 'postseason'
          AND ps.player_id = ANY(%s)
        ORDER BY s.year DESC
    """, (league, list(player_ids)))
    out = {}
    for r in cur.fetchall():
        r = dict(r)
        if r["player_id"] in out:
            continue
        st = r["stats"]
        if isinstance(st, str):
            try:
                st = json.loads(st)
            except ValueError:
                continue
        if not st:
            continue
        out[r["player_id"]] = dict(stats=st, year=r["year"],
                                   games_played=r["games_played"])
    return out


def playoff_split(reg_stats, post_stats, specs, sport):
    """Regular season versus postseason, on rate metrics only.

    Season totals cannot be compared against a three-game playoff run, so only
    per-90, per-game and percentage metrics are set side by side. The change is
    expressed against the player's own regular-season rate, which is the honest
    comparison: it asks whether he raised his level, not whether his team went
    deep.
    """
    rows = []
    for key, label, mode, higher in specs:
        if mode == "total":
            continue
        rv = metric_value(reg_stats, key, mode, sport)
        pv = metric_value(post_stats, key, mode, sport)
        if rv is None or pv is None:
            continue
        change = None
        if rv:
            change = round((pv - rv) / abs(rv) * 100.0, 1)
            if not higher:
                change = -change
        rows.append(dict(key=key, label=label, mode=mode,
                         regular=round(rv, 3), postseason=round(pv, 3),
                         change_pct=change, higher_is_better=higher))
    return rows


def money_for(cur, player_ids, league):
    """Return {player_id: {...}} on whichever axis this league is allowed."""
    axis, label = MONEY_AXIS.get(league, (None, None))
    if not axis or not player_ids:
        return {}, axis, label
    out = {}
    if axis == "salary":
        cur.execute("""SELECT player_id, avg_annual_value, guaranteed, source,
                              start_year, contract_type
                       FROM contracts WHERE player_id = ANY(%s)""", (list(player_ids),))
        for r in cur.fetchall():
            r = dict(r)
            amt = r["guaranteed"] or r["avg_annual_value"]
            if amt:
                out[r["player_id"]] = dict(amount=int(amt), currency="USD",
                                           amount_usd=int(amt),
                                           source=r["source"], as_of=r["start_year"],
                                           kind=r["contract_type"])
    else:
        cur.execute("""SELECT player_id, market_value_eur, market_value_usd,
                              contract_expires, agent_name, source, updated_at
                       FROM player_market_profile WHERE player_id = ANY(%s)""",
                    (list(player_ids),))
        for r in cur.fetchall():
            r = dict(r)
            if r["market_value_eur"]:
                out[r["player_id"]] = dict(
                    amount=int(r["market_value_eur"]), currency="EUR",
                    amount_usd=(int(r["market_value_usd"])
                                if r["market_value_usd"] else None),
                    source=r["source"],
                    as_of=r["updated_at"].date().isoformat() if r["updated_at"] else None,
                    contract_expires=(r["contract_expires"].isoformat()
                                      if r["contract_expires"] else None),
                    agent=r["agent_name"], kind="market_value")
    return out, axis, label


# ------------------------------------------------------------------ core

def history(name, league=None, max_seasons=30):
    """Every stored season for a player, with Python-computed aggregates.

    analyze() answers "how good is he this season". This answers "what does his
    record look like across the seasons we hold" - which is what career and
    multi-season comparison questions actually need. Without it the model does
    the arithmetic itself, and it will get some of it right and some of it
    wrong with identical confidence.
    """
    with get_conn() as c:
        cur = c.cursor()
        found = find_player(cur, name, league)
        if not found:
            return {"ok": False, "error": "no player named %r" % name}
        me = found[0]
        sport, lg = me["sport"], me["league"]
        group = POS_GROUP.get(sport, {}).get((me["position"] or "").upper())
        specs = metric_specs(sport, group) if group else []

        cur.execute("""
            SELECT s.year, s.season_type, ps.stats, ps.games_played, t.name AS team
            FROM player_seasons ps
            JOIN seasons s ON s.id = ps.season_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE ps.player_id = %s
            ORDER BY s.year, s.season_type
        """, (me["id"],))
        seasons, post = [], []
        for r in cur.fetchall():
            r = dict(r)
            st = r["stats"]
            if isinstance(st, str):
                try:
                    st = json.loads(st)
                except ValueError:
                    continue
            if not st:
                continue
            row = dict(year=r["year"], team=r["team"], games=r["games_played"],
                       values={})
            for key, label, mode, higher in specs:
                v = metric_value(st, key, mode, sport)
                if v is not None:
                    row["values"][label] = round(v, 3)
            (post if r["season_type"] == "postseason" else seasons).append(row)

        seasons = seasons[-max_seasons:]
        agg = {}
        for key, label, mode, higher in specs:
            vals = [sq["values"][label] for sq in seasons if label in sq["values"]]
            if not vals:
                continue
            best = max(vals) if higher else min(vals)
            best_year = next(sq["year"] for sq in seasons
                             if sq["values"].get(label) == best)
            entry = dict(seasons=len(vals), mean=round(sum(vals) / len(vals), 3),
                         best=best, best_year=best_year,
                         higher_is_better=higher)
            if mode == "total":
                entry["total"] = round(sum(vals), 3)
            agg[label] = entry

        return {
            "ok": True,
            "player": dict(id=me["id"], name=me["full_name"], league=lg,
                           sport=sport, position=me["position"],
                           age=age_from(me["birth_date"])),
            "seasons_held": [sq["year"] for sq in seasons],
            "season_rows": seasons,
            "postseason_rows": post,
            "aggregates": agg,
            "caveat": "These aggregates cover ONLY the seasons listed in "
                      "seasons_held. They are not career totals unless every "
                      "season of the career happens to be stored.",
        }


def analyze(name, league=None, comps=6):
    with get_conn() as c:
        cur = c.cursor()

        found = find_player(cur, name, league)
        if not found:
            return {"ok": False, "error": "no player named %r" % name}
        if len(found) > 1 and not league:
            return {"ok": False, "error": "ambiguous",
                    "candidates": [{"name": f["full_name"], "league": f["league"],
                                    "position": f["position"]} for f in found[:8]]}
        me = found[0]
        sport, lg = me["sport"], me["league"]
        group = POS_GROUP.get(sport, {}).get((me["position"] or "").upper())
        if not group:
            return {"ok": False, "error": "unmapped position %r for %s"
                                          % (me["position"], lg)}

        rows = cohort_rows(cur, lg, sport, group)
        mine = [r for r in rows if r["id"] == me["id"]]
        if not mine:
            return {"ok": False, "error": "no season stats stored for %s"
                                          % me["full_name"]}
        # Most recent season first, workload as the tie-break. "How good is he"
        # means now, not whichever year he happened to play the most games.
        mine = max(mine, key=lambda r: (r["year"] or 0, workload(r["stats"], sport)))
        my_stats, my_year = mine["stats"], mine["year"]

        # Curated league-leader rows (pre-1999 Wikipedia) hold a handful of
        # players per season. They answer "who led the league in 1972" but they
        # are not a cohort: ranking someone against the eight other people we
        # happen to hold would manufacture a percentile out of nothing.
        if (mine.get("source") or "") == "wikipedia_leaders":
            held = {}
            for key, label, mode, higher in metric_specs(sport, group):
                v = my_stats.get(key)
                if v is not None:
                    held[label] = v
            return {
                "ok": True, "mode": "leaders_only",
                "player": dict(id=me["id"], name=me["full_name"], league=lg,
                               sport=sport, position=me["position"],
                               position_group=group, age=age_from(me["birth_date"]),
                               team=mine["team_name"]),
                "season": dict(year=my_year, games_played=mine["games_played"]),
                "held": held,
                "note": ("Rigorlytics holds %s only as a league-leader record for "
                         "%s, not a full season of rosters. The figures above are "
                         "real and may be quoted. Percentiles, comparable players "
                         "and value bands CANNOT be computed for this season and "
                         "must not be stated or estimated - there is no cohort to "
                         "rank against." % (me["full_name"], my_year)),
                "confidence": dict(tier="low", reasons=[
                    "league-leader record only; no cohort exists for %s" % my_year]),
                "provenance": [dict(field="season statistics",
                                    source="Wikipedia (CC BY-SA)", as_of=my_year)],
            }

        # Rank within the same season. Pooling 1999-2025 into one cohort would
        # measure a 2021 quarterback against 2003 passing rules and report the
        # difference as if it were talent - the era error this engine exists to
        # avoid. A cohort is a season, not an archive.
        floor = MIN_WORKLOAD.get(sport, 0.0)
        peers = [r for r in rows
                 if r["id"] != me["id"] and r["year"] == my_year
                 and workload(r["stats"], sport) >= floor
                 and (r.get("source") or "") != "wikipedia_leaders"]
        my_age = age_from(me["birth_date"])

        # ---- metrics + percentiles (derived)
        specs = metric_specs(sport, group)
        metrics, zvec, covered = [], {}, 0
        for key, label, mode, higher in specs:
            mv = metric_value(my_stats, key, mode, sport)
            if mv is None:
                continue
            covered += 1
            pool = []
            for r in peers:
                pv = metric_value(r["stats"], key, mode, sport)
                if pv is not None:
                    pool.append(pv)
            flat = bool(pool) and max(pool) == min(pool)
            pr = None if flat else pct_rank(pool, mv)
            if pr is not None and not higher:
                pr = round(100.0 - pr, 1)
            mu = sum(pool) / len(pool) if pool else None
            sd = (math.sqrt(sum((v - mu) ** 2 for v in pool) / len(pool))
                  if pool and len(pool) > 1 else None)
            if sd:
                zvec[key] = ((mv - mu) / sd) * (1 if higher else -1)
            metrics.append(dict(key=key, label=label, mode=mode, value=round(mv, 3),
                                percentile=pr, no_variance=flat, cohort_n=len(pool),
                                cohort_median=round(median(pool), 3) if pool else None,
                                higher_is_better=higher))

        ranked = [m["percentile"] for m in metrics if m["percentile"] is not None]
        composite = round(sum(ranked) / len(ranked), 1) if ranked else None

        # ---- comparables (derived): nearest peers in z-space
        # Cohort mean/sd per metric are computed once, and each peer's value is
        # cached, so this is O(n*k) rather than O(n^2*k) -- it runs inside a
        # web request.
        comp_peers, age_band = peers, None
        if my_age is not None:
            for width in AGE_BANDS:
                sel = [r for r in peers if r["birth_date"] is not None
                       and abs(age_from(r["birth_date"]) - my_age) <= width]
                if len(sel) >= MIN_COMP_POOL:
                    comp_peers, age_band = sel, width
                    break

        spec_by_key = {s[0]: s for s in specs}
        stats_by_key, vals_by_peer = {}, []
        for key in zvec:
            mode = spec_by_key[key][2]
            pool = []
            for r in comp_peers:
                pool.append(metric_value(r["stats"], key, mode, sport))
            vals_by_peer.append((key, pool))
            clean = [v for v in pool if v is not None]
            if len(clean) < 2:
                stats_by_key[key] = None
                continue
            mu = sum(clean) / len(clean)
            sd = math.sqrt(sum((v - mu) ** 2 for v in clean) / len(clean))
            stats_by_key[key] = (mu, sd) if sd else None

        sims = []
        need = max(2, len(zvec) // 2)
        for i, r in enumerate(comp_peers):
            d, n = 0.0, 0
            for key, pool in vals_by_peer:
                ms = stats_by_key.get(key)
                pv = pool[i]
                if ms is None or pv is None:
                    continue
                mu, sd = ms
                d += (zvec[key] - (pv - mu) / sd) ** 2
                n += 1
            if n >= need:
                sims.append((math.sqrt(d / n), r))
        sims.sort(key=lambda x: x[0])
        near = sims[:comps]

        ids = [r["id"] for _, r in near] + [me["id"]]
        money, axis, axis_label = money_for(cur, ids, lg)
        post = postseason_for(cur, lg, ids)

        comparables = []
        for dist, r in near:
            m = money.get(r["id"])
            pp = post.get(r["id"])
            comparables.append(dict(
                player=r["full_name"], team=r["team_name"], position=r["position"],
                age=age_from(r["birth_date"]), distance=round(dist, 3),
                money=m,
                postseason=(dict(year=pp["year"], games=pp["games_played"],
                                 workload=workload(pp["stats"], sport),
                                 split=playoff_split(
                                     next((x["stats"] for x in rows
                                           if x["id"] == r["id"]), {}),
                                     pp["stats"], specs, sport))
                            if pp else None)))

        my_post = post.get(me["id"])
        if my_post:
            # postseason_for returns the most recent playoff row, which is not
            # necessarily the season being analysed. Setting a 2022 playoff rate
            # against a 2025 regular-season rate and calling the difference a
            # change reports a three-year era gap as form.
            same_season = (my_post["year"] == my_year)
            postseason = dict(
                has_data=True, year=my_post["year"],
                games=my_post["games_played"],
                workload=workload(my_post["stats"], sport),
                same_season=same_season,
                split=(playoff_split(my_stats, my_post["stats"], specs, sport)
                       if same_season else []),
                basis=("playoff rates against this player's own regular-season "
                       "rates" if same_season else
                       "playoff row is from %s but the analysed season is %s, "
                       "so no rate comparison is valid across that gap"
                       % (my_post["year"], my_year)))
        else:
            postseason = dict(
                has_data=False,
                note="No postseason appearances in the data for %s. That is an "
                     "absence of playoff games, not weak playoff performance, and "
                     "must not be read as a negative." % me["full_name"])

        # ---- market position (fact) + projection (inference)
        my_money = money.get(me["id"])
        peer_amounts = [c["money"]["amount"] for c in comparables if c.get("money")]
        band = None
        if len(peer_amounts) >= 3:
            lo = quantile(peer_amounts, 0.25)
            hi = quantile(peer_amounts, 0.75)
            mid = median(peer_amounts)
            band = dict(low=int(lo), mid=int(mid), high=int(hi),
                        currency=comparables[0]["money"]["currency"],
                        n=len(peer_amounts),
                        comp_age_median=median([c["age"] for c in comparables if c.get("age")]),
                        player_age=my_age,
                        age_band=age_band,
                        basis="interquartile range of the %d nearest statistical "
                              "comparables in the same league and position group%s"
                              % (len(peer_amounts),
                                 (", within %.1f years of age" % age_band)
                                 if age_band else " (age band could not be applied)"))
            usd = [c["money"].get("amount_usd") for c in comparables
                   if c.get("money") and c["money"].get("amount_usd")]
            if len(usd) == len(peer_amounts):
                band["low_usd"] = int(quantile(usd, 0.25))
                band["mid_usd"] = int(median(usd))
                band["high_usd"] = int(quantile(usd, 0.75))
            if my_money:
                a = my_money["amount"]
                band["actual"] = a
                if my_money.get("amount_usd"):
                    band["actual_usd"] = int(my_money["amount_usd"])
                band["verdict"] = ("above" if a > hi else
                                   "below" if a < lo else "within")
                band["gap_vs_mid"] = int(a - mid)

        # ---- confidence
        reasons, tier = [], "high"
        wl = workload(my_stats, sport)
        if wl < floor:
            tier = "low"
            reasons.append("only %s %s recorded, below the %s cohort floor"
                           % (int(wl), "minutes" if sport != "football" else "games",
                              int(floor)))
        if len(peers) < 20:
            tier = "low" if tier == "low" else "medium"
            reasons.append("small cohort: %d comparable players" % len(peers))
        if covered < max(2, len(specs) // 2):
            tier = "low"
            reasons.append("only %d of %d metrics available for this player"
                           % (covered, len(specs)))
        if axis and not peer_amounts:
            tier = "low" if tier == "low" else "medium"
            reasons.append("no %s data for the comparable set" % axis.replace("_", " "))
        if not reasons:
            reasons.append("full metric coverage against a cohort of %d peers"
                           % len(peers))

        return {
            "ok": True,
            "player": dict(id=me["id"], name=me["full_name"], league=lg, sport=sport,
                           position=me["position"], position_group=group,
                           age=age_from(me["birth_date"]), team=mine["team_name"],
                           headshot=me["headshot_url"]),
            "season": dict(year=my_year, workload=wl,
                           games_played=mine["games_played"]),
            "cohort": dict(league=lg, position_group=group, n=len(peers),
                           comparable_pool=len(comp_peers), age_band=age_band,
                           workload_floor=floor,
                           season=my_year,
                           definition="same league, same position group, SAME "
                                      "SEASON (%s), at least %d %s"
                                      % (my_year, floor,
                                         "minutes" if sport != "football" else "games")),
            "metrics": metrics,
            "composite_percentile": composite,
            "comparables": comparables,
            "postseason": postseason,
            "money": dict(axis=axis, axis_label=axis_label, player=my_money,
                          band=band),
            "confidence": dict(tier=tier, reasons=reasons,
                               metrics_covered=covered, metrics_possible=len(specs)),
            "provenance": [
                dict(field="season statistics", source="ESPN core API",
                     as_of=my_year),
                dict(field="money", source=(my_money or {}).get("source"),
                     as_of=(my_money or {}).get("as_of")),
            ],
            "claim_tiers": {
                "fact": ["season statistics", "money figures", "roster and position"],
                "derived": ["percentiles", "per-90 and per-game rates",
                            "composite percentile", "comparable set"],
                "inference": ["projected value band"],
            },
            "narration_rules": [
                "Use only numbers present in this object.",
                "Never state a salary for a league whose money axis is null.",
                "Lead with the confidence caveat when tier is not high.",
                "Describe the band as a projection from comparables, not a valuation.",
            ],
        }


# ------------------------------------------------------------------ cli

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", required=True)
    ap.add_argument("--league", default=None)
    ap.add_argument("--comps", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    obj = analyze(a.player, a.league, a.comps)
    if a.json:
        print(json.dumps(obj, indent=2, default=str))
        return
    if not obj.get("ok"):
        print("ERROR: %s" % obj.get("error"))
        for cand in obj.get("candidates", []):
            print("   %s (%s, %s)" % (cand["name"], cand["league"], cand["position"]))
        return

    p, m = obj["player"], obj["money"]
    print("%s - %s %s, age %s, %s" % (p["name"], p["league"], p["position"],
                                      p["age"], p["team"]))
    print("cohort: %d %s in %s   season %s"
          % (obj["cohort"]["n"], p["position_group"], p["league"], obj["season"]["year"]))
    print("composite percentile: %s" % obj["composite_percentile"])
    print("confidence: %s (%s)" % (obj["confidence"]["tier"],
                                   "; ".join(obj["confidence"]["reasons"])))
    print("\nmetrics")
    for x in obj["metrics"]:
        print("   %-22s %-10s pct=%-6s median=%s"
              % (x["label"], x["value"], x["percentile"], x["cohort_median"]))
    print("\ncomparables")
    for cmp_ in obj["comparables"]:
        mo = cmp_["money"]
        if mo:
            cash = "%s %s" % (mo["currency"], format(mo["amount"], ","))
            if mo.get("amount_usd") and mo["currency"] != "USD":
                cash += "  (USD %s)" % format(mo["amount_usd"], ",")
        else:
            cash = "-"
        print("   %-24s %-22s d=%-6s %s"
              % (cmp_["player"], cmp_["team"] or "-", cmp_["distance"], cash))
    ps = obj.get("postseason") or {}
    if ps.get("has_data"):
        print("\npostseason (%s, %s games)" % (ps.get("year"), ps.get("games")))
        for r in ps.get("split", []):
            chg = "" if r.get("change_pct") is None else "  %+.1f%%" % r["change_pct"]
            print("   %-22s %-10s -> %-10s%s"
                  % (r["label"], r["regular"], r["postseason"], chg))
    else:
        print("\npostseason: none on record")

    if m["band"]:
        b = m["band"]
        print("\nprojected band (%s): %s %s - %s   mid %s"
              % (m["axis"], b["currency"], format(b["low"], ","),
                 format(b["high"], ","), format(b["mid"], ",")))
        if b.get("mid_usd"):
            print("                 USD %s - %s   mid %s"
                  % (format(b["low_usd"], ","), format(b["high_usd"], ","),
                     format(b["mid_usd"], ",")))
        if "actual" in b:
            line = "actual: %s %s" % (b["currency"], format(b["actual"], ","))
            if b.get("actual_usd") and b["currency"] != "USD":
                line += " (USD %s)" % format(b["actual_usd"], ",")
            print("%s -> %s (gap vs mid %s)"
                  % (line, b["verdict"], format(b["gap_vs_mid"], ",")))
    elif not m["axis"]:
        print("\nno money axis for %s - percentile and comparables only" % p["league"])


if __name__ == "__main__":
    main()
