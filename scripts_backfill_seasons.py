#!/usr/bin/env python3
"""
Rigorlytics - season-stat backfill for NFL, CFB, EPL, MLS, WNBA.

Writes player_seasons rows with the same flattened "category.statName" JSONB
convention already used by the NBA/NFL rows (e.g. general.PER, offensive.points).

Uses sports.core.api.espn.com exclusively. site.api.espn.com is IP-blocked from
some hosts (returns 403 for every league), so it is never called here.

Usage:
    python scripts_backfill_seasons.py --probe wnba          # 1 athlete, show keys, write nothing
    python scripts_backfill_seasons.py --leagues wnba --limit 5 --dry-run
    python scripts_backfill_seasons.py --leagues epl
    python scripts_backfill_seasons.py --leagues mls
    python scripts_backfill_seasons.py --leagues nfl --roster-only
    python scripts_backfill_seasons.py --leagues cfb         # slow: ~13k athletes
    python scripts_backfill_seasons.py --leagues epl --reseed --seed-only

Safe to re-run: existing (player_id, season_id) rows are updated, not duplicated.
"""

import os, sys, json, time, argparse, urllib.request

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.getcwd())
from app.db import get_conn

UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net)"}
CORE = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{path}"

LEAGUES = {
    "nfl":  dict(code="NFL",  name="National Football League",                sport="football",   path="nfl",              year=2025, groups=None, seed=False, stype=2, post=3),
    "cfb":  dict(code="CFB",  name="NCAA Football",                           sport="football",   path="college-football", year=2025, groups="80", seed=True,  stype=2, post=3),
    "wnba": dict(code="WNBA", name="Women's National Basketball Association", sport="basketball", path="wnba",             year=2025, groups=None, seed=False, stype=2, post=3),
    "nba":  dict(code="NBA",  name="National Basketball Association",         sport="basketball", path="nba",              year=2025, groups=None, seed=False, stype=2, post=3),
    "epl":  dict(code="EPL",  name="Premier League",                          sport="soccer",     path="eng.1",            year=2025, groups=None, seed=True,  stype=2, post=None),
    "mls":  dict(code="MLS",  name="Major League Soccer",                     sport="soccer",     path="usa.1",            year=2025, groups=None, seed=True,  stype=1, post=3),
}


# ------------------------------------------------------------------ http

def fetch(url, tries=3, pause=0.4, timeout=25):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError("fetch failed %s: %s" % (url, last))


def core_refs(url, tries=3):
    """Page through a core-API $ref collection, returning every item's $ref."""
    refs = []
    page = 1
    while True:
        u = url + ("&" if "?" in url else "?") + "page=%d" % page
        d = fetch(u, tries=tries)
        for it in (d.get("items") or []):
            if it.get("$ref"):
                refs.append(it["$ref"])
        if page >= int(d.get("pageCount") or 1):
            break
        page += 1
    return refs


# ------------------------------------------------------------------ parsing

def flatten_stats(payload):
    """ESPN athlete statistics -> {'category.statName': float}, matching existing rows."""
    out = {}
    splits = payload.get("splits") or {}
    for cat in (splits.get("categories") or []):
        cname = cat.get("name") or "general"
        for st in (cat.get("stats") or []):
            n = st.get("name")
            if not n:
                continue
            v = st.get("value")
            if v is None:
                continue
            try:
                out["%s.%s" % (cname, n)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def norm_player(a):
    """Core-API athlete document -> players-table row."""
    pos = a.get("position") or {}
    hs = a.get("headshot") or {}
    ht = a.get("height")
    wt = a.get("weight")
    dob = a.get("dateOfBirth") or ""
    return dict(
        external_id=str(a.get("id")) if a.get("id") is not None else None,
        full_name=a.get("fullName") or a.get("displayName"),
        position=pos.get("abbreviation") or pos.get("name"),
        birth_date=dob[:10] or None,
        height_inches=int(ht) if isinstance(ht, (int, float)) else None,
        weight_lbs=int(wt) if isinstance(wt, (int, float)) else None,
        headshot_url=hs.get("href"),
        jersey=a.get("jersey"),
        active=bool(a.get("active", True)),
    )


# ------------------------------------------------------------------ db

def league_id(cur, cfg, create=True):
    cur.execute("SELECT id FROM leagues WHERE code=%s", (cfg["code"],))
    r = cur.fetchone()
    if r:
        return r["id"] if hasattr(r, "keys") else r[0]
    if not create:
        return None
    cur.execute("INSERT INTO leagues (code, name, sport) VALUES (%s,%s,%s) RETURNING id",
                (cfg["code"], cfg["name"], cfg["sport"]))
    r = cur.fetchone()
    return r["id"] if hasattr(r, "keys") else r[0]


def season_id(cur, lid, year, season_type="regular"):
    cur.execute("SELECT id FROM seasons WHERE league_id=%s AND year=%s AND season_type=%s",
                (lid, year, season_type))
    r = cur.fetchone()
    if r:
        return r["id"] if hasattr(r, "keys") else r[0]
    cur.execute("INSERT INTO seasons (league_id, year, season_type) VALUES (%s,%s,%s) RETURNING id",
                (lid, year, season_type))
    r = cur.fetchone()
    return r["id"] if hasattr(r, "keys") else r[0]


def team_refs(cfg, year):
    base = CORE.format(sport=cfg["sport"], path=cfg["path"])
    if cfg["groups"]:
        url = base + "/seasons/%s/types/2/groups/%s/teams?limit=1000" % (year, cfg["groups"])
    else:
        url = base + "/seasons/%s/teams?limit=1000" % year
    return core_refs(url)


def ensure_team(cur, lid, t):
    """Upsert a teams row from a core-API team document; return teams.id."""
    ext = str(t.get("id")) if t.get("id") is not None else None
    if not ext:
        return None
    cur.execute("SELECT id FROM teams WHERE league_id=%s AND external_id=%s", (lid, ext))
    r = cur.fetchone()
    if r:
        return r["id"] if hasattr(r, "keys") else r[0]
    cur.execute("""INSERT INTO teams (league_id, external_id, name, abbreviation, city, active)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (lid, ext, t.get("displayName") or t.get("name"),
                 t.get("abbreviation"), t.get("location"), True))
    r = cur.fetchone()
    return r["id"] if hasattr(r, "keys") else r[0]


def seed_players(cur, cfg, lid, year, limit=None, pause=0.12, conn=None):
    """Seed players + teams from the core API.

    Returns (added, roster) where roster maps players.id -> teams.id for every
    athlete currently on a roster, whether newly inserted or already present.
    """
    trefs = team_refs(cfg, year)
    if limit:
        trefs = trefs[:limit]
    print("    %d teams" % len(trefs))
    added = skipped = 0
    roster = {}
    for i, tref in enumerate(trefs, 1):
        base = tref.split("?")[0]
        try:
            tdoc = fetch(base, tries=2)
        except Exception as e:
            print("    ! team %s: %s" % (base[-16:], str(e)[:60]))
            continue
        tid = ensure_team(cur, lid, tdoc)
        try:
            arefs = core_refs(base + "/athletes?limit=500", tries=2)
        except Exception as e:
            print("    ! athletes %s: %s" % (base[-16:], str(e)[:60]))
            continue
        for aref in arefs:
            try:
                a = fetch(aref, tries=2)
            except Exception:
                continue
            p = norm_player(a)
            if not p["external_id"] or not p["full_name"]:
                continue
            cur.execute("SELECT id FROM players WHERE league_id=%s AND external_id=%s",
                        (lid, p["external_id"]))
            ex = cur.fetchone()
            if ex:
                pid = ex["id"] if hasattr(ex, "keys") else ex[0]
                skipped += 1
            else:
                cur.execute("""INSERT INTO players
                    (league_id, external_id, full_name, position, birth_date,
                     height_inches, weight_lbs, headshot_url, jersey, active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (lid, p["external_id"], p["full_name"], p["position"], p["birth_date"],
                     p["height_inches"], p["weight_lbs"], p["headshot_url"], p["jersey"], p["active"]))
                r = cur.fetchone()
                pid = r["id"] if hasattr(r, "keys") else r[0]
                added += 1
            roster[pid] = tid
            time.sleep(pause)
        # Commit per team. CFB is 146 programs and several hours; holding one
        # transaction across that guarantees the pooler drops it and every
        # inserted row is rolled back.
        if conn is not None:
            try:
                conn.commit()
            except Exception as e:
                print("    ! commit %s: %s" % (i, str(e)[:60]))
        print("    team %d/%d  %-24s added=%d existing=%d" % (
            i, len(trefs), (tdoc.get("abbreviation") or "")[:24], added, skipped))
    return added, roster


def upsert_season_row(cur, player_id, sid, stats, team_id=None, dry=False):
    gp = stats.get("general.gamesPlayed")
    gs = stats.get("general.gamesStarted")
    per = stats.get("general.PER")
    ts = (stats.get("offensive.trueShootingPct") or stats.get("general.trueShootingPct"))
    row = dict(
        games_played=int(gp) if gp is not None else None,
        games_started=int(gs) if gs is not None else None,
        stats=json.dumps(stats), per=per, true_shooting=ts, source="espn",
    )
    if dry:
        return "DRY"
    cur.execute("SELECT id FROM player_seasons WHERE player_id=%s AND season_id=%s", (player_id, sid))
    ex = cur.fetchone()
    if ex:
        eid = ex["id"] if hasattr(ex, "keys") else ex[0]
        cur.execute("""UPDATE player_seasons SET games_played=%s, games_started=%s, stats=%s::jsonb,
                       per=%s, true_shooting=%s, source=%s,
                       team_id=COALESCE(%s, team_id), updated_at=now() WHERE id=%s""",
                    (row["games_played"], row["games_started"], row["stats"],
                     row["per"], row["true_shooting"], row["source"], team_id, eid))
        return "UPD"
    cur.execute("""INSERT INTO player_seasons
        (player_id, season_id, team_id, games_played, games_started, stats, per, true_shooting, source, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,now())""",
        (player_id, sid, team_id, row["games_played"], row["games_started"], row["stats"],
         row["per"], row["true_shooting"], row["source"]))
    return "INS"


# ------------------------------------------------------------------ main

def stats_url(cfg, year, ext_id, espn_type=None):
    if espn_type is None:
        espn_type = cfg.get("stype", 2)
    return (CORE.format(sport=cfg["sport"], path=cfg["path"])
            + "/seasons/%s/types/%s/athletes/%s/statistics" % (year, espn_type, ext_id))


def do_probe(key):
    cfg = LEAGUES[key]
    with get_conn() as c:
        cur = c.cursor()
        lid = league_id(cur, cfg, create=False)
        if lid is None:
            print("league %s not in DB yet - run without --probe to seed it" % cfg["code"]); return
        cur.execute("SELECT id, external_id, full_name FROM players WHERE league_id=%s LIMIT 1", (lid,))
        r = cur.fetchone()
        if not r:
            print("no players for %s yet" % cfg["code"]); return
        r = dict(r) if hasattr(r, "keys") else {"id": r[0], "external_id": r[1], "full_name": r[2]}
    print("probe:", r["full_name"], "espn id", r["external_id"])
    payload = fetch(stats_url(cfg, cfg["year"], r["external_id"]))
    st = flatten_stats(payload)
    print("flattened keys: %d" % len(st))
    for k in sorted(st)[:40]:
        print("   %-38s %s" % (k, st[k]))


def run(keys, year_override, limit, dry, pause, reseed, seed_only, roster_only,
        postseason=False):
    for key in keys:
        cfg = LEAGUES[key]
        year = year_override or cfg["year"]
        print("=" * 60)
        espn_type = cfg.get("post") if postseason else cfg.get("stype", 2)
        sql_type = "postseason" if postseason else "regular"
        if postseason and not espn_type:
            print("%s has no postseason - skipping" % cfg["code"])
            continue
        print("%s  season %s  (%s, espn type %s)"
              % (cfg["code"], year, sql_type, espn_type))
        with get_conn() as c:
            cur = c.cursor()
            lid = league_id(cur, cfg)
            sid = season_id(cur, lid, year, sql_type)
            c.commit()
            cur.execute("SELECT count(*) AS n FROM players WHERE league_id=%s", (lid,))
            r = cur.fetchone()
            n = r["n"] if hasattr(r, "keys") else r[0]
            print("  %d players already in DB" % n)

            roster = {}
            if reseed or roster_only or (cfg["seed"] and n == 0):
                print("  seeding rosters + teams from core API")
                added, roster = seed_players(cur, cfg, lid, year, limit=limit, conn=c)
                c.commit()
                print("  seeded %d new players across %d roster spots" % (added, len(roster)))
            if seed_only:
                continue

            if roster_only and roster:
                cur.execute("""SELECT id, external_id, full_name FROM players
                               WHERE id = ANY(%s) AND external_id IS NOT NULL
                               ORDER BY id""", (list(roster.keys()),))
            else:
                cur.execute("""SELECT id, external_id, full_name FROM players
                               WHERE league_id=%s AND external_id IS NOT NULL
                               ORDER BY id""", (lid,))
            players = [dict(x) if hasattr(x, "keys") else {"id": x[0], "external_id": x[1], "full_name": x[2]}
                       for x in cur.fetchall()]
            if limit and not roster_only:
                players = players[:limit]
            # ESPN echoes the regular-season line for leagues that have no
            # postseason, so refuse to store a playoff row identical to it.
            reg = {}
            if postseason:
                cur.execute("""SELECT ps.player_id, ps.stats FROM player_seasons ps
                               JOIN seasons s ON s.id = ps.season_id
                               WHERE s.league_id=%s AND s.year=%s
                                 AND s.season_type='regular'""", (lid, year))
                for r in cur.fetchall():
                    r = dict(r)
                    st0 = r["stats"]
                    if isinstance(st0, str):
                        try:
                            st0 = json.loads(st0)
                        except ValueError:
                            st0 = None
                    if st0:
                        reg[r["player_id"]] = {k: float(v) for k, v in st0.items()
                                               if isinstance(v, (int, float))}
            dup = 0
            print("  %d players to process" % len(players))
            ins = upd = skip = err = 0
            for i, p in enumerate(players, 1):
                try:
                    payload = fetch(stats_url(cfg, year, p["external_id"], espn_type),
                                    tries=2)
                except Exception:
                    skip += 1; continue
                st = flatten_stats(payload)
                if not st or not any(v for v in st.values()):
                    skip += 1; continue
                if postseason and reg.get(p["id"]) == st:
                    dup += 1; continue
                try:
                    res = upsert_season_row(cur, p["id"], sid, st,
                                            team_id=roster.get(p["id"]), dry=dry)
                    if res == "INS": ins += 1
                    elif res == "UPD": upd += 1
                except Exception as e:
                    err += 1
                    print("    ! %s: %s" % (p["full_name"], str(e)[:70]))
                if i % 50 == 0:
                    if not dry: c.commit()
                    print("    %d/%d  ins=%d upd=%d skip=%d err=%d" % (i, len(players), ins, upd, skip, err))
                time.sleep(pause)
            if not dry: c.commit()
            print("  DONE %s %s: inserted=%d updated=%d no-stats=%d "
                  "identical-to-regular=%d errors=%d"
                  % (cfg["code"], sql_type, ins, upd, skip, dup, err))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="wnba,epl,mls,nfl,cfb")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--probe", default=None)
    ap.add_argument("--pause", type=float, default=0.25)
    ap.add_argument("--reseed", action="store_true", help="seed rosters even if players already exist")
    ap.add_argument("--seed-only", action="store_true", help="seed rosters and stop before stats")
    ap.add_argument("--postseason", action="store_true",
                    help="pull playoff stats into season_type='postseason'")
    ap.add_argument("--roster-only", action="store_true",
                    help="seed from current rosters, then pull stats for those players only")
    a = ap.parse_args()
    if a.probe:
        if a.probe not in LEAGUES: sys.exit("unknown league: %s" % a.probe)
        return do_probe(a.probe)
    keys = [k.strip().lower() for k in a.leagues.split(",") if k.strip()]
    bad = [k for k in keys if k not in LEAGUES]
    if bad: sys.exit("unknown league(s): %s" % bad)
    run(keys, a.year, a.limit, a.dry_run, a.pause, a.reseed, a.seed_only, a.roster_only,
        postseason=a.postseason)


if __name__ == "__main__":
    main()
