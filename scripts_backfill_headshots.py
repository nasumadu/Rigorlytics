"""
Rigorlytics - backfill players.headshot_url from nflverse rosters.

WHY THIS EXISTS
---------------
Measured 2026-11-11, among NFL players holding a top-5 season in a stat
between 2000 and 2025:

    passing yards      78 / 130   (60%)
    passing TD         78 / 130   (60%)
    receiving yards    44 / 130   (34%)
    rushing yards      30 / 130   (23%)

A leaderboard card rendering four grey monograms and one photograph reads as
broken software, so this runs before that card ships.

The data was never missing. scripts_ingest_nflverse.py already reads
headshot_url out of the roster files and writes it -- but only on INSERT. A
player row created earlier by scripts_backfill_seasons.py (ESPN) keeps its
NULL forever, which is why quarterbacks, whom ESPN covered, score nearly
three times better than running backs. This updates in place instead.

MATCHING
--------
Per player, in order, stopping at the first hit:

  1. external_id = gsis_id   -- rows created by the nflverse ingest
  2. external_id = espn_id   -- rows created by the ESPN backfill
  3. normalised full name, ONLY when that name maps to exactly one player
     in the roster data, AND only when the two positions do not conflict.
     "Michael Thomas" is three different NFL players; handing the wrong one
     a photograph is worse than leaving the monogram, because a wrong face
     looks like a correct answer. Position is compared by coarse bucket,
     not exact string, because ESPN and nflverse spell positions
     differently -- the check is there to catch a quarterback being handed
     a cornerback's face, not to demand the two sources agree on wording.

A dry run prints a sample of accepted name matches and every rejected
position conflict, because name matching is the majority of the matches
and it is the one route that can be confidently wrong.

SAFETY
------
Writes one column, players.headshot_url, and only where it is currently
NULL. Never overwrites an existing photo. Re-running it is a no-op for
rows already filled, so it is safe to run again after any future ingest.
Pass --dry-run to see the counts without writing.

USAGE
-----
    python3 scripts_backfill_headshots.py --dry-run
    python3 scripts_backfill_headshots.py
    python3 scripts_backfill_headshots.py --years 2010-2025
"""

import argparse
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas is required: pip install pandas pyarrow")

try:
    from app.db import get_conn
except ImportError:
    from db import get_conn


ROSTER_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
              "rosters/roster_%d.parquet")

# nflverse has renamed columns across releases, so never index a column by a
# single hardcoded name -- a rename would silently produce zero matches and
# look like "the data isn't there" rather than "the column moved".
COL_NAME = ("full_name", "player_name", "display_name", "football_name")
COL_HEAD = ("headshot_url", "headshot")
COL_GSIS = ("gsis_id", "player_id")
COL_ESPN = ("espn_id",)
COL_POS = ("position", "depth_chart_position", "ngs_position")

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}

# Coarse position buckets, used only to REJECT a name match where both
# sides state a position and the two disagree. ESPN and nflverse spell
# positions differently, so an exact comparison would throw away good
# matches; a bucket comparison only catches the real conflicts -- a
# quarterback being handed a cornerback's face.
POS_BUCKETS = {
    "QB": "QB",
    "RB": "RB", "FB": "RB", "HB": "RB",
    "WR": "REC", "TE": "REC",
    "C": "OL", "G": "OL", "OG": "OL", "T": "OL", "OT": "OL", "OL": "OL",
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL",
    "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB", "EDGE": "LB",
    "CB": "DB", "S": "DB", "SS": "DB", "FS": "DB", "DB": "DB", "SAF": "DB",
    "K": "K", "P": "K", "PK": "K", "LS": "K",
}


def bucket(pos):
    """Coarse position family, or None when it cannot be determined."""
    if not pos:
        return None
    return POS_BUCKETS.get(str(pos).strip().upper())


def pick(df, candidates):
    """First column in `candidates` that the frame actually has."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def norm(name):
    """Fold a name to a comparison key: case, punctuation and suffixes."""
    if not name:
        return ""
    s = str(name).lower().strip()
    s = s.replace("'", "").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z\s-]", "", s)
    parts = [p for p in re.split(r"[\s-]+", s) if p]
    while len(parts) > 2 and parts[-1] in SUFFIXES:
        parts.pop()
    return " ".join(parts)


def fetch_rosters(years):
    """Download each roster file and return one concatenated frame."""
    frames = []
    tmp = tempfile.mkdtemp(prefix="nflverse-rosters-")
    for y in years:
        url = ROSTER_URL % y
        path = os.path.join(tmp, "roster_%d.parquet" % y)
        try:
            urllib.request.urlretrieve(url, path)
        except urllib.error.HTTPError as e:
            print("  %d  skipped (HTTP %s)" % (y, e.code))
            continue
        except Exception as e:
            print("  %d  skipped (%s)" % (y, e))
            continue
        try:
            df = pd.read_parquet(path)
        except Exception as e:
            print("  %d  unreadable (%s)" % (y, e))
            continue
        print("  %d  %5d roster rows" % (y, len(df)))
        frames.append(df)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def build_maps(df):
    """gsis -> url, espn -> url, and name -> (url, position, roster_name)
    for names that belong to exactly one player in the roster data."""
    c_name = pick(df, COL_NAME)
    c_head = pick(df, COL_HEAD)
    c_gsis = pick(df, COL_GSIS)
    c_espn = pick(df, COL_ESPN)
    c_pos = pick(df, COL_POS)

    if not c_head:
        sys.exit("No headshot column in the roster data (looked for %s). "
                 "Column list: %s" % (", ".join(COL_HEAD), list(df.columns)))

    print("\ncolumns in use: name=%s headshot=%s gsis=%s espn=%s pos=%s"
          % (c_name, c_head, c_gsis, c_espn, c_pos))

    by_gsis, by_espn = {}, {}
    # name -> first (url, position, display name) seen, plus the set of
    # distinct players under that name so an ambiguous one is dropped
    # rather than guessed.
    name_rec, name_ids = {}, {}

    for row in df.itertuples(index=False):
        url = getattr(row, c_head, None)
        if not url or not isinstance(url, str) or not url.startswith("http"):
            continue

        gsis = getattr(row, c_gsis, None) if c_gsis else None
        if gsis and isinstance(gsis, str):
            by_gsis.setdefault(gsis, url)

        espn = getattr(row, c_espn, None) if c_espn else None
        if espn is not None and str(espn) not in ("nan", "None", ""):
            # espn_id arrives as a float in some releases: 3139477.0
            key = str(espn)
            if key.endswith(".0"):
                key = key[:-2]
            by_espn.setdefault(key, url)

        if c_name:
            raw = getattr(row, c_name, None)
            n = norm(raw)
            if n:
                pos = getattr(row, c_pos, None) if c_pos else None
                name_rec.setdefault(n, (url, pos, raw))
                name_ids.setdefault(n, set()).add(gsis or url)

    by_name = {n: r for n, r in name_rec.items() if len(name_ids[n]) == 1}
    dropped = len(name_rec) - len(by_name)

    print("roster index: %d by gsis, %d by espn, %d by unique name "
          "(%d ambiguous names dropped)"
          % (len(by_gsis), len(by_espn), len(by_name), dropped))
    return by_gsis, by_espn, by_name


def coverage(cur):
    cur.execute("""
        SELECT count(*) AS total, count(p.headshot_url) AS have
        FROM players p
        JOIN leagues l ON l.id = p.league_id
        WHERE l.code = 'NFL'
          AND EXISTS (SELECT 1 FROM player_seasons ps WHERE ps.player_id = p.id)
    """)
    r = dict(cur.fetchone())
    return r["total"], r["have"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1999-2025",
                    help="roster years to read, e.g. 2010-2025")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change and write nothing")
    args = ap.parse_args()

    lo, _, hi = args.years.partition("-")
    years = range(int(lo), int(hi or lo) + 1)

    print("Reading nflverse rosters %s" % args.years)
    df = fetch_rosters(years)
    if df is None:
        sys.exit("No roster files could be read. Check network access to "
                 "github.com from this host.")

    by_gsis, by_espn, by_name = build_maps(df)

    with get_conn() as c:
        cur = c.cursor()

        total, have = coverage(cur)
        print("\nbefore: %d of %d NFL players with season data have a photo "
              "(%.1f%%)" % (have, total, 100.0 * have / total if total else 0))

        # Only players who actually have season data. A photo on a row no
        # question can ever reach is work for nothing, and it inflates the
        # match count so the real coverage number gets harder to read.
        cur.execute("""
            SELECT p.id, p.external_id, p.full_name, p.position
            FROM players p
            JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL' AND p.headshot_url IS NULL
              AND EXISTS (SELECT 1 FROM player_seasons ps
                          WHERE ps.player_id = p.id)
        """)
        candidates = [dict(r) for r in cur.fetchall()]
        print("%d NFL players with season data have no photo" % len(candidates))

        hits = {"gsis": 0, "espn": 0, "name": 0}
        updates = []
        name_sample = []
        pos_conflicts = []

        for p in candidates:
            ext = p["external_id"]
            url = how = None
            if ext and ext in by_gsis:
                url, how = by_gsis[ext], "gsis"
            elif ext and str(ext) in by_espn:
                url, how = by_espn[str(ext)], "espn"
            else:
                n = norm(p["full_name"])
                rec = by_name.get(n)
                if rec:
                    r_url, r_pos, r_name = rec
                    db_b, ros_b = bucket(p["position"]), bucket(r_pos)
                    if db_b and ros_b and db_b != ros_b:
                        # Same name, different kind of player. Refuse it.
                        pos_conflicts.append(
                            (p["full_name"], p["position"], r_name, r_pos))
                        continue
                    url, how = r_url, "name"
                    if len(name_sample) < 15:
                        name_sample.append(
                            (p["full_name"], p["position"] or "?",
                             r_name, str(r_pos or "?")))
            if url:
                hits[how] += 1
                updates.append((url, p["id"]))

        print("\nmatched %d of %d:  %d by gsis_id, %d by espn_id, "
              "%d by unique name"
              % (len(updates), len(candidates),
                 hits["gsis"], hits["espn"], hits["name"]))
        print("rejected %d name matches on a position conflict"
              % len(pos_conflicts))

        if pos_conflicts:
            print("\n  position conflicts rejected (first 10):")
            for db_n, db_p, r_n, r_p in pos_conflicts[:10]:
                print("    %-24s %-4s  vs roster %-24s %s"
                      % (db_n, db_p or "?", r_n, r_p or "?"))

        if name_sample:
            print("\n  name matches accepted, for review (first 15):")
            print("    %-26s %-5s %-26s %s"
                  % ("DATABASE", "POS", "ROSTER", "POS"))
            for db_n, db_p, r_n, r_p in name_sample:
                flag = "" if norm(db_n) == norm(r_n) else "   <-- spelling differs"
                print("    %-26s %-5s %-26s %-5s%s"
                      % (db_n[:26], db_p, str(r_n)[:26], r_p, flag))

        if args.dry_run:
            print("\n--dry-run: nothing written.")
            for url, pid in updates[:5]:
                print("  would set %s -> %s" % (pid, url))
            return

        if not updates:
            print("Nothing to do.")
            return

        # The WHERE guard repeats headshot_url IS NULL so a concurrent writer
        # cannot be clobbered between the SELECT above and this UPDATE.
        cur.executemany("""
            UPDATE players
               SET headshot_url = %s, updated_at = now()
             WHERE id = %s AND headshot_url IS NULL
        """, updates)
        c.commit()

        total, have = coverage(cur)
        print("after:  %d of %d NFL players with season data have a photo "
              "(%.1f%%)" % (have, total, 100.0 * have / total if total else 0))


if __name__ == "__main__":
    main()
