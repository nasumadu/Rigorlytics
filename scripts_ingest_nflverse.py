#!/usr/bin/env python3
"""
Rigorlytics - complete NFL seasons from nflverse (1999 onward).

ESPN gives one athlete per request, which does not scale to twenty-seven
seasons, and its pre-1999 rosters are wrong. nflverse publishes one flat file
per season - complete rosters, regular and postseason - plus the advanced
metrics ESPN never exposed: EPA, CPOE, air yards, PACR.

Stats are written in the same flattened "category.statName" convention the rest
of the database uses, so app/valuation.py keeps working unchanged. Advanced
figures land under "advanced." and every remaining numeric column is preserved
under "nflverse." so nothing is thrown away.

Players are matched to existing rows by name and position before any insert, so
this does not duplicate the ESPN-sourced roster.

    python scripts_ingest_nflverse.py --probe 2020
    python scripts_ingest_nflverse.py --years 2020 --dry-run
    python scripts_ingest_nflverse.py --years 2015-2025
    python scripts_ingest_nflverse.py --years 1999-2025 --types reg,post
"""

import os, sys, csv, io, re, json, math, time, argparse, unicodedata, urllib.request

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.getcwd())
from app.db import get_conn

BASE = ("https://github.com/nflverse/nflverse-data/releases/download/"
        "stats_player/stats_player_%s_%s.csv")
UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net)"}
CACHE = "/tmp/nflverse"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# nflverse column -> our canonical flattened key. Anything not listed that is
# numeric still gets carried through under "nflverse.".
CANON = {
    "games": "general.gamesPlayed",
    "passing_yards": "passing.passingYards",
    "passing_tds": "passing.passingTouchdowns",
    "passing_interceptions": "passing.interceptions",
    "completions": "passing.completions",
    "attempts": "passing.passingAttempts",
    "sacks_suffered": "passing.sacked",
    "passing_first_downs": "passing.passingFirstDowns",
    "passing_air_yards": "passing.airYards",
    "passing_yards_after_catch": "passing.yardsAfterCatch",
    "carries": "rushing.rushingAttempts",
    "rushing_yards": "rushing.rushingYards",
    "rushing_tds": "rushing.rushingTouchdowns",
    "rushing_first_downs": "rushing.rushingFirstDowns",
    "rushing_fumbles_lost": "rushing.fumblesLost",
    "receptions": "receiving.receptions",
    "targets": "receiving.receivingTargets",
    "receiving_yards": "receiving.receivingYards",
    "receiving_tds": "receiving.receivingTouchdowns",
    "receiving_first_downs": "receiving.receivingFirstDowns",
    "receiving_air_yards": "receiving.airYards",
    "def_tackles": "defensive.totalTackles",
    "def_tackles_solo": "defensive.soloTackles",
    "def_sacks": "defensive.sacks",
    "def_tackles_for_loss": "defensive.tacklesForLoss",
    "def_interceptions": "defensiveInterceptions.interceptions",
    "def_pass_defended": "defensive.passesDefended",
    "def_qb_hits": "defensive.QBHits",
    "def_fumbles_forced": "defensive.fumblesForced",
}
ADVANCED = {
    "passing_epa": "advanced.passingEPA",
    "rushing_epa": "advanced.rushingEPA",
    "receiving_epa": "advanced.receivingEPA",
    "passing_cpoe": "advanced.CPOE",
    "pacr": "advanced.PACR",
    "racr": "advanced.RACR",
    "target_share": "advanced.targetShare",
    "air_yards_share": "advanced.airYardsShare",
    "wopr": "advanced.WOPR",
    "def_epa": "advanced.defensiveEPA",
}
SKIP_COLS = {"player_id", "player_name", "player_display_name", "position",
             "position_group", "headshot_url", "season", "season_type",
             "recent_team", "team", "opponent_team", "week"}


# ------------------------------------------------------------------ helpers

def norm_name(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("-", " ").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(p for p in s.split() if p and p not in SUFFIXES)


def num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # nflverse emits Infinity for rate columns with a zero denominator - a
    # receiver with no targets gets target_share = inf. json.dumps writes that
    # literally and Postgres rejects it as invalid JSON, killing the load.
    return f if math.isfinite(f) else None


def load_season(year, kind, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "stats_player_%s_%s.csv" % (kind, year))
    if refresh or not os.path.exists(path):
        url = BASE % (kind, year)
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
        except Exception as e:
            return None, str(e)[:70]
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f)), None


def to_stats(row):
    """nflverse row -> flattened stat dict in our house convention."""
    out = {}
    for col, val in row.items():
        if col in SKIP_COLS:
            continue
        v = num(val)
        if v is None:
            continue
        if col in CANON:
            out[CANON[col]] = v
        elif col in ADVANCED:
            out[ADVANCED[col]] = v
        else:
            out["nflverse." + col] = v
    # Derived rates the valuation engine expects to find.
    att = out.get("rushing.rushingAttempts")
    if att:
        out["rushing.yardsPerRushAttempt"] = round(
            (out.get("rushing.rushingYards") or 0.0) / att, 3)
    rec = out.get("receiving.receptions")
    if rec:
        out["receiving.yardsPerReception"] = round(
            (out.get("receiving.receivingYards") or 0.0) / rec, 3)
    cmp_, patt = out.get("passing.completions"), out.get("passing.passingAttempts")
    if cmp_ is not None and patt:
        out["passing.completionPct"] = round(100.0 * cmp_ / patt, 3)
    return out


# ------------------------------------------------------------------ db

def league_and_season(cur, year, kind):
    cur.execute("SELECT id FROM leagues WHERE code='NFL'")
    r = cur.fetchone()
    if not r:
        cur.execute("""INSERT INTO leagues (code, name, sport)
                       VALUES ('NFL','National Football League','football')
                       RETURNING id""")
        r = cur.fetchone()
    lid = dict(r)["id"] if hasattr(r, "keys") else r[0]
    stype = "regular" if kind == "reg" else "postseason"
    cur.execute("""SELECT id FROM seasons WHERE league_id=%s AND year=%s
                   AND season_type=%s""", (lid, year, stype))
    r = cur.fetchone()
    if r:
        return lid, (dict(r)["id"] if hasattr(r, "keys") else r[0]), stype
    cur.execute("""INSERT INTO seasons (league_id, year, season_type)
                   VALUES (%s,%s,%s) RETURNING id""", (lid, year, stype))
    r = cur.fetchone()
    return lid, (dict(r)["id"] if hasattr(r, "keys") else r[0]), stype


def player_index(cur, lid):
    """Existing NFL players by normalised name, and by name+position."""
    cur.execute("""SELECT id, full_name, position, external_id
                   FROM players WHERE league_id=%s""", (lid,))
    by_name, by_np = {}, {}
    for r in cur.fetchall():
        r = dict(r)
        n = norm_name(r["full_name"])
        if not n:
            continue
        by_name.setdefault(n, []).append(r["id"])
        by_np.setdefault((n, (r["position"] or "").upper()), []).append(r["id"])
    return by_name, by_np


def team_index(cur, lid):
    cur.execute("""SELECT id, abbreviation FROM teams WHERE league_id=%s""", (lid,))
    return {(dict(r)["abbreviation"] or "").upper(): dict(r)["id"]
            for r in cur.fetchall() if dict(r)["abbreviation"]}


def ensure_team(cur, lid, abbr, teams):
    if not abbr:
        return None
    key = abbr.upper()
    if key in teams:
        return teams[key]
    cur.execute("""INSERT INTO teams (league_id, external_id, name, abbreviation, active)
                   VALUES (%s,%s,%s,%s,TRUE) RETURNING id""",
                (lid, "nflverse:" + key, key, key))
    r = cur.fetchone()
    tid = dict(r)["id"] if hasattr(r, "keys") else r[0]
    teams[key] = tid
    return tid


def resolve_player(cur, lid, row, by_name, by_np):
    """Match to an existing player, else insert one. Returns (id, created)."""
    name = row.get("player_display_name") or row.get("player_name")
    pos = (row.get("position") or "").upper()
    n = norm_name(name)
    if not n:
        return None, False
    hit = by_np.get((n, pos), [])
    if len(hit) == 1:
        return hit[0], False
    hit = by_name.get(n, [])
    if len(hit) == 1:
        return hit[0], False
    if len(hit) > 1:
        return hit[0], False          # same name and league; take the first
    cur.execute("""INSERT INTO players
        (league_id, external_id, full_name, position, headshot_url, active)
        VALUES (%s,%s,%s,%s,%s,TRUE) RETURNING id""",
        (lid, "nflverse:" + str(row.get("player_id")), name, pos or None,
         row.get("headshot_url") or None))
    r = cur.fetchone()
    pid = dict(r)["id"] if hasattr(r, "keys") else r[0]
    by_name.setdefault(n, []).append(pid)
    by_np.setdefault((n, pos), []).append(pid)
    return pid, True


def upsert(cur, pid, sid, tid, stats, games):
    cur.execute("""SELECT id, source FROM player_seasons
                   WHERE player_id=%s AND season_id=%s""", (pid, sid))
    ex = cur.fetchone()
    blob = json.dumps(stats)
    if ex:
        ex = dict(ex)
        cur.execute("""UPDATE player_seasons
                       SET stats=%s::jsonb, games_played=%s,
                           team_id=COALESCE(%s, team_id),
                           source='nflverse', updated_at=now()
                       WHERE id=%s""", (blob, games, tid, ex["id"]))
        return "UPD"
    cur.execute("""INSERT INTO player_seasons
        (player_id, season_id, team_id, games_played, stats, source, updated_at)
        VALUES (%s,%s,%s,%s,%s::jsonb,'nflverse',now())""",
        (pid, sid, tid, games, blob))
    return "INS"


# ------------------------------------------------------------------ main

def parse_years(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def do_probe(year):
    for kind in ("reg", "post"):
        rows, err = load_season(year, kind)
        if err:
            print("%s %s -> %s" % (year, kind, err)); continue
        print("\n%s %s: %d rows" % (year, kind, len(rows)))
        top = sorted(rows, key=lambda r: num(r.get("passing_yards")) or 0,
                     reverse=True)[:5]
        for r in top:
            print("   %-24s %-4s %s yds, %s TD, EPA %s"
                  % (r.get("player_display_name"), r.get("position"),
                     r.get("passing_yards"), r.get("passing_tds"),
                     r.get("passing_epa")))
        st = to_stats(top[0])
        print("   mapped keys for leader: %d" % len(st))
        for k in sorted(st)[:12]:
            print("      %-34s %s" % (k, st[k]))


def run(years, kinds, dry, refresh):
    total = dict(ins=0, upd=0, new_players=0, skipped=0)
    with get_conn() as c:
        cur = c.cursor()
        cur.execute("SELECT id FROM leagues WHERE code='NFL'")
        r = cur.fetchone()
        lid = (dict(r)["id"] if hasattr(r, "keys") else r[0]) if r else None
        if lid is None:
            lid, _, _ = league_and_season(cur, years[0], "reg")
            c.commit()
        by_name, by_np = player_index(cur, lid)
        teams = team_index(cur, lid)
        print("existing NFL players: %d   teams: %d" % (len(by_name), len(teams)))

        for year in years:
            for kind in kinds:
                rows, err = load_season(year, kind, refresh)
                if err:
                    print("  %s %s: unavailable (%s)" % (year, kind, err)); continue
                lid, sid, stype = league_and_season(cur, year, kind)
                if not dry:
                    c.commit()
                ins = upd = new = skip = 0
                for row in rows:
                    stats = to_stats(row)
                    if not stats or not any(v for v in stats.values()):
                        skip += 1; continue
                    pid, created = resolve_player(cur, lid, row, by_name, by_np)
                    if pid is None:
                        skip += 1; continue
                    new += 1 if created else 0
                    if dry:
                        continue
                    tid = ensure_team(cur, lid, row.get("recent_team")
                                      or row.get("team"), teams)
                    res = upsert(cur, pid, sid, tid, stats,
                                 int(num(row.get("games")) or 0) or None)
                    ins += res == "INS"
                    upd += res == "UPD"
                if not dry:
                    c.commit()
                print("  %s %-4s rows=%-5d inserted=%-5d updated=%-5d new players=%-4d skipped=%d"
                      % (year, stype, len(rows), ins, upd, new, skip))
                total["ins"] += ins; total["upd"] += upd
                total["new_players"] += new; total["skipped"] += skip

    print("\nDONE  inserted=%d updated=%d new players=%d skipped=%d%s"
          % (total["ins"], total["upd"], total["new_players"], total["skipped"],
             "   (DRY RUN - nothing written)" if dry else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1999-2025")
    ap.add_argument("--types", default="reg,post")
    ap.add_argument("--probe", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.probe:
        return do_probe(a.probe)
    kinds = [k.strip() for k in a.types.split(",") if k.strip() in ("reg", "post")]
    run(parse_years(a.years), kinds, a.dry_run, a.refresh)


if __name__ == "__main__":
    main()
