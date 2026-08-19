#!/usr/bin/env python3
"""
Rigorlytics - MLS salary ingest from the MLS Players Association salary guide.

The MLSPA publishes a CSV twice a season listing every player's annualized base
salary and guaranteed compensation. This is a players-union primary source, so
unlike European wage data it is authoritative rather than estimated.

    First Name, Last Name, Club Name, Position, PA Base Salary, CY Guaranteed Comp (PA)

Mapping into `contracts`:
    avg_annual_value = annualized base salary
    guaranteed       = guaranteed compensation (base + annualized bonuses)
    contract_type    = 'mlspa_disclosure'
    source           = 'MLSPA'

Usage:
    python scripts_ingest_mlspa.py                  # dry run: match report only
    python scripts_ingest_mlspa.py --write          # actually write contracts
    python scripts_ingest_mlspa.py --url <csv-url>  # a different edition
"""

import os, sys, csv, re, io, argparse, unicodedata, urllib.request

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.getcwd())
from app.db import get_conn

DEFAULT_URL = ("http://s3.amazonaws.com/mlspa/Spring-2026-MLSPA-Salary-Guide.csv"
               "?mtime=20260512175019")
UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net)"}
SEASON_YEAR = 2026
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


# ------------------------------------------------------------------ helpers

def norm_name(s):
    """Casefold, strip accents and punctuation, drop generational suffixes."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("-", " ").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    parts = [p for p in s.split() if p and p not in SUFFIXES]
    return " ".join(parts)


def money(s):
    """'$88,025.00' -> 88025 (whole dollars)."""
    if s is None:
        return None
    s = str(s).strip().replace("$", "").replace(",", "").replace('"', "")
    if not s or s in ("-", "NA", "N/A"):
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def fetch_csv(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def pick(row, *candidates):
    """Column names drift between editions; match loosely."""
    keys = {norm_name(k): k for k in row.keys() if k}
    for c in candidates:
        n = norm_name(c)
        if n in keys:
            return row[keys[n]]
    for c in candidates:
        n = norm_name(c)
        for k_norm, k_real in keys.items():
            if n in k_norm:
                return row[k_real]
    return None


# ------------------------------------------------------------------ db

def load_players(cur):
    """Build several name indexes for MLS players, plus each player's club.

    ESPN and the MLSPA spell names differently often enough that exact full-name
    matching alone leaves ~28% on the table, so we fall back progressively:
    full name -> first+last tokens -> surname within the same club -> surname
    plus first initial league-wide. Every fallback requires a *unique* hit.
    """
    cur.execute("""SELECT p.id, p.full_name, p.position,
                          (SELECT ps.team_id FROM player_seasons ps
                            WHERE ps.player_id = p.id AND ps.team_id IS NOT NULL
                            ORDER BY ps.id DESC LIMIT 1) AS team_id
                   FROM players p JOIN leagues l ON l.id = p.league_id
                   WHERE l.code = 'MLS'""")
    idx = dict(full={}, firstlast={}, surname_team={}, surname_initial={})
    meta = {}
    for r in cur.fetchall():
        r = dict(r)
        pid, n = r["id"], norm_name(r["full_name"])
        meta[pid] = r
        if not n:
            continue
        toks = n.split()
        idx["full"].setdefault(n, []).append(pid)
        if len(toks) >= 2:
            idx["firstlast"].setdefault("%s %s" % (toks[0], toks[-1]), []).append(pid)
        if toks:
            sur = toks[-1]
            idx["surname_team"].setdefault((sur, r["team_id"]), []).append(pid)
            idx["surname_initial"].setdefault((sur, toks[0][:1]), []).append(pid)
    return idx, meta


def resolve(full, team_id, idx):
    """Return (player_id, method) or (None, reason)."""
    n = norm_name(full)
    if not n:
        return None, "empty"
    toks = n.split()
    hit = idx["full"].get(n, [])
    if len(hit) == 1:
        return hit[0], "full"
    if len(hit) > 1:
        return None, "ambiguous"
    if len(toks) >= 2:
        hit = idx["firstlast"].get("%s %s" % (toks[0], toks[-1]), [])
        if len(hit) == 1:
            return hit[0], "firstlast"
        if len(hit) > 1:
            return None, "ambiguous"
    if toks and team_id is not None:
        hit = idx["surname_team"].get((toks[-1], team_id), [])
        if len(hit) == 1:
            return hit[0], "surname+club"
        if len(hit) > 1:
            return None, "ambiguous"
    if len(toks) >= 2:
        hit = idx["surname_initial"].get((toks[-1], toks[0][:1]), [])
        if len(hit) == 1:
            return hit[0], "surname+initial"
        if len(hit) > 1:
            return None, "ambiguous"
    return None, "missing"


def load_teams(cur):
    cur.execute("""SELECT t.id, t.name, t.abbreviation
                   FROM teams t JOIN leagues l ON l.id = t.league_id
                   WHERE l.code = 'MLS'""")
    out = {}
    for r in cur.fetchall():
        r = dict(r)
        out[norm_name(r["name"])] = r["id"]
    return out


def match_team(club, teams):
    """MLSPA club names are shorter than ESPN's ('Atlanta United' vs '... FC')."""
    n = norm_name(club)
    if n in teams:
        return teams[n]
    for tname, tid in teams.items():
        if n and (n in tname or tname in n):
            return tid
    return None


def upsert_contract(cur, player_id, team_id, base, gtd):
    cur.execute("""SELECT id FROM contracts
                   WHERE player_id=%s AND source='MLSPA' AND start_year=%s""",
                (player_id, SEASON_YEAR))
    ex = cur.fetchone()
    if ex:
        eid = ex["id"] if hasattr(ex, "keys") else ex[0]
        cur.execute("""UPDATE contracts SET team_id=%s, avg_annual_value=%s,
                       guaranteed=%s WHERE id=%s""", (team_id, base, gtd, eid))
        return "UPD"
    cur.execute("""INSERT INTO contracts
        (player_id, team_id, start_year, end_year, years,
         avg_annual_value, guaranteed, contract_type, source, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'mlspa_disclosure','MLSPA',now())""",
        (player_id, team_id, SEASON_YEAR, SEASON_YEAR, 1, base, gtd))
    return "INS"


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--write", action="store_true", help="write to contracts (default: dry run)")
    ap.add_argument("--show-unmatched", type=int, default=15)
    a = ap.parse_args()

    text = fetch_csv(a.url)
    rows = list(csv.DictReader(io.StringIO(text)))
    print("csv rows: %d" % len(rows))
    if not rows:
        sys.exit("empty csv")
    print("columns: %s" % list(rows[0].keys()))

    with get_conn() as c:
        cur = c.cursor()

        cur.execute("""SELECT count(*) AS n, min(avg_annual_value) AS lo,
                              max(avg_annual_value) AS hi
                       FROM contracts""")
        r = dict(cur.fetchone())
        print("existing contracts: n=%s aav range %s..%s" % (r["n"], r["lo"], r["hi"]))

        idx, meta = load_players(cur)
        teams = load_teams(cur)
        print("mls players in db: %d   mls teams in db: %d" % (len(meta), len(teams)))

        matched = ambiguous = unmatched = 0
        ins = upd = 0
        methods = {}
        misses, samples = [], []

        for row in rows:
            first = (pick(row, "First Name") or "").strip()
            last = (pick(row, "Last Name") or "").strip()
            club = (pick(row, "Club Name", "Club") or "").strip()
            base = money(pick(row, "PA Base Salary", "Base Salary"))
            gtd = money(pick(row, "CY Guaranteed Comp (PA)", "Guaranteed Comp",
                             "Guaranteed Compensation"))
            full = ("%s %s" % (first, last)).strip()
            if not full:
                continue

            tid = match_team(club, teams)
            pid, how = resolve(full, tid, idx)
            if pid is None:
                if how == "ambiguous":
                    ambiguous += 1
                else:
                    unmatched += 1
                    if len(misses) < a.show_unmatched:
                        misses.append("%s (%s)" % (full, club))
                continue

            methods[how] = methods.get(how, 0) + 1
            matched += 1
            if len(samples) < 6:
                samples.append((full, club, base, gtd))
            if a.write:
                res = upsert_contract(cur, pid, tid, base, gtd)
                ins += (res == "INS"); upd += (res == "UPD")

        if a.write:
            c.commit()

        print("\nmatched=%d  ambiguous=%d  unmatched=%d" % (matched, ambiguous, unmatched))
        print("match methods: %s" % dict(sorted(methods.items(), key=lambda x: -x[1])))
        print("sample:")
        for s in samples:
            print("   %-26s %-22s base=%-10s gtd=%s" % s)
        if misses:
            print("unmatched examples:")
            for m in misses:
                print("   %s" % m)
        print("\n%s" % ("WROTE contracts: inserted=%d updated=%d" % (ins, upd)
                        if a.write else "DRY RUN - nothing written (use --write)"))


if __name__ == "__main__":
    main()
