#!/usr/bin/env python3
"""
Rigorlytics - market values and transfer fees from the transfermarkt-datasets
project (CC0-1.0, refreshed weekly).

The Premier League publishes no wage data, so market value and transfer fee are
the only defensible money axes for EPL players. This ingest keys Transfermarkt
records to the ESPN-sourced players already in the database and writes three
additive tables. Nothing existing is modified.

    player_market_profile   current + peak value, contract expiry, agent
    player_market_values    the historical valuation time series
    player_transfers        completed moves with fees

Matching is name + date-of-birth first (near-unambiguous), then progressively
looser, and every fallback must resolve to exactly one player.

Usage:
    python scripts_ingest_transfermarkt.py                 # dry run, match report
    python scripts_ingest_transfermarkt.py --write         # create tables + load
    python scripts_ingest_transfermarkt.py --refresh       # re-download sources
"""

import os, sys, csv, io, re, gzip, argparse, unicodedata, urllib.request

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.getcwd())
from app.db import get_conn

BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"
UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net)"}
CACHE = "/tmp/tm_cache"
COMPS = {"GB1": "EPL", "MLS1": "MLS"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

DDL = [
    """CREATE TABLE IF NOT EXISTS player_market_profile (
        id serial PRIMARY KEY,
        player_id integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        tm_player_id integer,
        market_value_eur bigint,
        highest_market_value_eur bigint,
        contract_expires date,
        agent_name text,
        foot text,
        sub_position text,
        source text NOT NULL DEFAULT 'transfermarkt',
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT player_market_profile_uniq UNIQUE (player_id, source))""",
    """CREATE TABLE IF NOT EXISTS player_market_values (
        id serial PRIMARY KEY,
        player_id integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        as_of date NOT NULL,
        market_value_eur bigint,
        club_name text,
        source text NOT NULL DEFAULT 'transfermarkt',
        CONSTRAINT player_market_values_uniq UNIQUE (player_id, as_of, source))""",
    """CREATE TABLE IF NOT EXISTS player_transfers (
        id serial PRIMARY KEY,
        player_id integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        transfer_date date,
        season text,
        from_club text,
        to_club text,
        fee_eur bigint,
        market_value_eur bigint,
        source text NOT NULL DEFAULT 'transfermarkt',
        CONSTRAINT player_transfers_uniq UNIQUE (player_id, transfer_date, from_club, to_club, source))""",
    "CREATE INDEX IF NOT EXISTS pmv_player_idx ON player_market_values (player_id, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS ptr_player_idx ON player_transfers (player_id, transfer_date DESC)",
]


# ------------------------------------------------------------------ helpers

def norm_name(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("-", " ").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(p for p in s.split() if p and p not in SUFFIXES)


def num(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s or s.lower() in ("nan", "na", "n/a", "-", "null"):
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def day(s):
    if not s:
        return None
    s = str(s).strip()[:10]
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def load_csv(name, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + ".csv")
    if refresh or not os.path.exists(path):
        url = "%s/%s.csv.gz" % (BASE, name)
        print("  downloading %s" % url)
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r:
            data = gzip.decompress(r.read())
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ matching

def build_index(cur):
    """Index EPL + MLS players from our DB by several keys."""
    cur.execute("""SELECT p.id, p.full_name, p.birth_date, l.code AS league
                   FROM players p JOIN leagues l ON l.id = p.league_id
                   WHERE l.code IN ('EPL','MLS')""")
    idx = dict(name_dob={}, name={}, firstlast_dob={}, firstlast={})
    n = 0
    for r in cur.fetchall():
        r = dict(r)
        nm = norm_name(r["full_name"])
        if not nm:
            continue
        n += 1
        dob = r["birth_date"].isoformat() if r["birth_date"] else None
        toks = nm.split()
        fl = "%s %s" % (toks[0], toks[-1]) if len(toks) >= 2 else nm
        idx["name"].setdefault(nm, []).append(r["id"])
        idx["firstlast"].setdefault(fl, []).append(r["id"])
        if dob:
            idx["name_dob"].setdefault((nm, dob), []).append(r["id"])
            idx["firstlast_dob"].setdefault((fl, dob), []).append(r["id"])
    return idx, n


def resolve(tm_name, tm_dob, idx):
    nm = norm_name(tm_name)
    if not nm:
        return None, "empty"
    toks = nm.split()
    fl = "%s %s" % (toks[0], toks[-1]) if len(toks) >= 2 else nm
    for key, bucket, label in (
        ((nm, tm_dob), "name_dob", "name+dob"),
        ((fl, tm_dob), "firstlast_dob", "firstlast+dob"),
        (nm, "name", "name"),
        (fl, "firstlast", "firstlast"),
    ):
        if isinstance(key, tuple) and not key[1]:
            continue
        hit = idx[bucket].get(key, [])
        if len(hit) == 1:
            return hit[0], label
        if len(hit) > 1:
            return None, "ambiguous"
    return None, "missing"


# ------------------------------------------------------------------ writing

def bulk(cur, sql, rows, page=500):
    """Multi-row INSERT without psycopg2.extras.

    execute_values needs a raw psycopg2 connection; app.db returns a wrapper,
    so we build the VALUES tuples ourselves and let the driver bind params.
    """
    if not rows:
        return 0
    ncol = len(rows[0])
    tmpl = "(" + ",".join(["%s"] * ncol) + ")"
    done = 0
    for i in range(0, len(rows), page):
        chunk = rows[i:i + page]
        stmt = sql.replace("VALUES %s", "VALUES " + ",".join([tmpl] * len(chunk)))
        params = [v for r in chunk for v in r]
        cur.execute(stmt, params)
        done += len(chunk)
    return done


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--show-unmatched", type=int, default=12)
    a = ap.parse_args()

    print("loading transfermarkt sources")
    tm_players = load_csv("players", a.refresh)
    print("  players rows: %d" % len(tm_players))

    pool = [p for p in tm_players
            if (p.get("current_club_domestic_competition_id") or "").strip() in COMPS]
    print("  in EPL/MLS clubs: %d" % len(pool))

    with get_conn() as c:
        cur = c.cursor()
        idx, ours = build_index(cur)
        print("  our EPL+MLS players: %d" % ours)

        tm_to_pid, methods, misses = {}, {}, []
        for p in pool:
            pid, how = resolve(p.get("name"), day(p.get("date_of_birth")), idx)
            if pid is None:
                if len(misses) < a.show_unmatched and how == "missing":
                    misses.append("%s (%s)" % (p.get("name"), p.get("current_club_name")))
                methods[how] = methods.get(how, 0) + 1
                continue
            tm_to_pid[int(p["player_id"])] = pid
            methods[how] = methods.get(how, 0) + 1

        matched = len(tm_to_pid)
        print("\nmatched %d / %d transfermarkt players" % (matched, len(pool)))
        print("methods: %s" % dict(sorted(methods.items(), key=lambda x: -x[1])))
        if misses:
            print("unmatched examples:")
            for m in misses:
                print("   %s" % m)
        if not matched:
            sys.exit("no matches - aborting")

        # Transfermarkt can carry more than one record per real player (old and
        # current profiles), so collapse to one row per player_id before insert;
        # ON CONFLICT cannot touch the same row twice in a single statement.
        by_pid = {}
        for p in pool:
            pid = tm_to_pid.get(int(p["player_id"]))
            if not pid:
                continue
            row = (pid, num(p.get("player_id")), num(p.get("market_value_in_eur")),
                   num(p.get("highest_market_value_in_eur")),
                   day(p.get("contract_expiration_date")),
                   (p.get("agent_name") or None), (p.get("foot") or None),
                   (p.get("sub_position") or None))
            prev = by_pid.get(pid)
            if prev is None or (row[2] or 0) > (prev[2] or 0):
                by_pid[pid] = row
        profiles = list(by_pid.values())
        if len(profiles) != len(tm_to_pid):
            print("  collapsed %d duplicate transfermarkt profiles"
                  % (len(tm_to_pid) - len(profiles)))

        print("\nloading valuations + transfers")
        vals = load_csv("player_valuations", a.refresh)
        trs = load_csv("transfers", a.refresh)
        print("  valuation rows: %d   transfer rows: %d" % (len(vals), len(trs)))

        seen_v = set()
        vrows = []
        for v in vals:
            pid = tm_to_pid.get(num(v.get("player_id")) or -1)
            d = day(v.get("date"))
            if not pid or not d or (pid, d) in seen_v:
                continue
            seen_v.add((pid, d))
            vrows.append((pid, d, num(v.get("market_value_in_eur")), v.get("current_club_name") or None))

        seen_t = set()
        trows = []
        for t in trs:
            pid = tm_to_pid.get(num(t.get("player_id")) or -1)
            d = day(t.get("transfer_date"))
            if not pid:
                continue
            key = (pid, d, t.get("from_club_name"), t.get("to_club_name"))
            if key in seen_t:
                continue
            seen_t.add(key)
            trows.append((pid, d, t.get("transfer_season") or None,
                          t.get("from_club_name") or None, t.get("to_club_name") or None,
                          num(t.get("transfer_fee")), num(t.get("market_value_in_eur"))))

        print("  -> %d profiles, %d valuations, %d transfers for our players"
              % (len(profiles), len(vrows), len(trows)))

        if not a.write:
            print("\nDRY RUN - nothing written (use --write)")
            return

        for stmt in DDL:
            cur.execute(stmt)
        c.commit()
        print("tables ready")

        n1 = bulk(cur, """INSERT INTO player_market_profile
            (player_id, tm_player_id, market_value_eur, highest_market_value_eur,
             contract_expires, agent_name, foot, sub_position) VALUES %s
            ON CONFLICT ON CONSTRAINT player_market_profile_uniq DO UPDATE SET
              market_value_eur = EXCLUDED.market_value_eur,
              highest_market_value_eur = EXCLUDED.highest_market_value_eur,
              contract_expires = EXCLUDED.contract_expires,
              agent_name = EXCLUDED.agent_name,
              updated_at = now()""", profiles)
        c.commit()

        n2 = bulk(cur, """INSERT INTO player_market_values
            (player_id, as_of, market_value_eur, club_name) VALUES %s
            ON CONFLICT ON CONSTRAINT player_market_values_uniq DO NOTHING""", vrows)
        c.commit()

        n3 = bulk(cur, """INSERT INTO player_transfers
            (player_id, transfer_date, season, from_club, to_club, fee_eur, market_value_eur)
            VALUES %s
            ON CONFLICT ON CONSTRAINT player_transfers_uniq DO NOTHING""", trows)
        c.commit()

        print("WROTE profiles=%d valuations=%d transfers=%d" % (n1, n2, n3))

        cur.execute("""SELECT p.full_name, mp.market_value_eur, mp.contract_expires, mp.agent_name
                       FROM player_market_profile mp JOIN players p ON p.id = mp.player_id
                       ORDER BY mp.market_value_eur DESC NULLS LAST LIMIT 8""")
        print("\ntop valuations now in db:")
        for r in cur.fetchall():
            r = dict(r)
            print("   %-24s EUR %-12s expires=%-12s agent=%s"
                  % (r["full_name"], r["market_value_eur"], r["contract_expires"], r["agent_name"]))


if __name__ == "__main__":
    main()
