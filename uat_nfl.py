#!/usr/bin/env python3
"""
uat_nfl.py -- User Acceptance Testing harness for the NFL vertical of Rigorlytics.

Run from the project root (~/rigorlytics) with the venv active:

    python3 uat_nfl.py data       # database coverage only   (no network, no API cost)
    python3 uat_nfl.py lookup     # name resolution          (ESPN search, free)
    python3 uat_nfl.py compare    # comparison-card builder  (DB only, free)
    python3 uat_nfl.py live       # today's NFL scoreboard   (ESPN, free)
    python3 uat_nfl.py rag        # full answers             (COSTS Claude API credits)
    python3 uat_nfl.py all        # data + lookup + compare + live
    python3 uat_nfl.py all+rag    # everything

Writes a markdown summary to uat_nfl_report.md in the current directory.

Design notes
------------
Every check is wrapped so one broken call cannot abort the run. Where a module's
public function name is uncertain the harness probes for it and reports what it
found instead of raising, so the report stays useful as the codebase moves.

Status meanings:
    PASS  the behaviour the product promises actually happened
    FAIL  a real defect a user would hit
    WARN  a known limitation (source gap, thin coverage) -- not a code bug
    SKIP  could not be exercised in this environment
"""

import os
import sys
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = []
START = time.time()

SECTION_ORDER = ["data", "lookup", "compare", "live", "rag"]


# ----------------------------------------------------------------------------
# result collection
# ----------------------------------------------------------------------------

def record(section, name, status, detail=""):
    RESULTS.append({
        "section": section,
        "name": name,
        "status": status,
        "detail": str(detail)[:400],
    })
    icon = {"PASS": "ok  ", "FAIL": "FAIL", "WARN": "warn", "SKIP": "skip"}.get(status, "?   ")
    line = "  [%s] %s" % (icon, name)
    if detail:
        line += "  --  %s" % str(detail)[:150]
    print(line, flush=True)


def guard(section, name):
    """Decorator-ish helper: run fn, record an unexpected exception as FAIL."""
    def wrapper(fn):
        try:
            fn()
        except Exception as exc:
            record(section, name, "FAIL", "exception: %s: %s" % (type(exc).__name__, exc))
            if os.environ.get("UAT_TRACE"):
                traceback.print_exc()
    return wrapper


def banner(text):
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74, flush=True)


# ----------------------------------------------------------------------------
# module probing -- tolerate renamed functions rather than crashing
# ----------------------------------------------------------------------------

def find_callable(module, names):
    """Return (name, fn) for the first attribute in names that is callable."""
    for n in names:
        fn = getattr(module, n, None)
        if callable(fn):
            return n, fn
    return None, None


# ============================================================================
# SECTION 1 -- DATA COVERAGE
# ============================================================================

def section_data():
    banner("SECTION 1 / DATA COVERAGE  (how much NFL is actually in Postgres)")
    sec = "data"

    try:
        from app.db import query, query_one
    except Exception as exc:
        record(sec, "import app.db", "SKIP", "cannot import: %s" % exc)
        return

    try:
        query_one("SELECT 1 AS ok")
    except Exception as exc:
        record(sec, "database reachable", "FAIL",
               "connection failed (is DATABASE_URL set?): %s" % exc)
        return
    record(sec, "database reachable", "PASS")

    # which columns does players actually have -- keeps later queries honest
    cols = set()
    try:
        for r in query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'players'
        """):
            cols.add(r["column_name"])
    except Exception as exc:
        record(sec, "inspect players schema", "WARN", exc)

    # ---- roster size -------------------------------------------------------
    @guard(sec, "NFL players present")
    def _():
        row = query_one("""
            SELECT count(*) AS n FROM players p
            JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL'
        """)
        n = row["n"] if row else 0
        if n == 0:
            record(sec, "NFL players present", "FAIL", "zero NFL player rows")
        else:
            record(sec, "NFL players present", "PASS", "%s players" % f"{n:,}")

    # ---- stat coverage -----------------------------------------------------
    @guard(sec, "NFL stat coverage")
    def _():
        row = query_one("""
            SELECT
              (SELECT count(*) FROM players p
                 JOIN leagues l ON l.id = p.league_id
                WHERE l.code = 'NFL') AS players,
              (SELECT count(DISTINCT ps.player_id) FROM player_seasons ps
                 JOIN players p ON p.id = ps.player_id
                 JOIN leagues l ON l.id = p.league_id
                WHERE l.code = 'NFL') AS with_stats,
              (SELECT count(*) FROM player_seasons ps
                 JOIN players p ON p.id = ps.player_id
                 JOIN leagues l ON l.id = p.league_id
                WHERE l.code = 'NFL') AS season_rows
        """)
        players = row["players"] or 0
        with_stats = row["with_stats"] or 0
        rows = row["season_rows"] or 0
        pct = (100.0 * with_stats / players) if players else 0.0
        detail = "%s of %s players have stats (%.1f%%), %s season rows" % (
            f"{with_stats:,}", f"{players:,}", pct, f"{rows:,}")
        # A question about any NFL player is a coin flip below ~25% coverage.
        status = "PASS" if pct >= 25 else ("WARN" if pct >= 2 else "FAIL")
        record(sec, "NFL stat coverage", status, detail)

    # ---- season span -------------------------------------------------------
    @guard(sec, "season span")
    def _():
        row = query_one("""
            SELECT min(s.year) AS first, max(s.year) AS last, count(DISTINCT s.year) AS yrs
            FROM player_seasons ps
            JOIN seasons s ON s.id = ps.season_id
            JOIN leagues l ON l.id = s.league_id
            WHERE l.code = 'NFL'
        """)
        if not row or row["first"] is None:
            record(sec, "season span", "FAIL", "no NFL season rows at all")
            return
        detail = "%s-%s (%s distinct years)" % (row["first"], row["last"], row["yrs"])
        if row["first"] > 2002:
            record(sec, "season span", "WARN", detail + " -- no pre-2002 history")
        else:
            record(sec, "season span", "PASS", detail)

    # ---- current season present -------------------------------------------
    @guard(sec, "current season loaded")
    def _():
        yr = datetime.now().year
        row = query_one("""
            SELECT count(*) AS n FROM player_seasons ps
            JOIN seasons s ON s.id = ps.season_id
            JOIN leagues l ON l.id = s.league_id
            WHERE l.code = 'NFL' AND s.year = %s
        """, (yr,))
        n = row["n"] if row else 0
        if n == 0:
            record(sec, "current season loaded", "FAIL",
                   "zero rows for %s -- every current-season question falls back to ESPN" % yr)
        else:
            record(sec, "current season loaded", "PASS", "%s rows for %s" % (n, yr))

    # ---- position mix ------------------------------------------------------
    @guard(sec, "position mix on players with stats")
    def _():
        if "position" not in cols:
            record(sec, "position mix on players with stats", "SKIP", "no position column")
            return
        rows = query("""
            SELECT coalesce(nullif(p.position, ''), '(blank)') AS pos, count(*) AS n
            FROM (SELECT DISTINCT ps.player_id FROM player_seasons ps) d
            JOIN players p ON p.id = d.player_id
            JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL'
            GROUP BY 1 ORDER BY n DESC LIMIT 12
        """)
        if not rows:
            record(sec, "position mix on players with stats", "FAIL", "none found")
            return
        mix = ", ".join("%s:%s" % (r["pos"], r["n"]) for r in rows)
        have = {r["pos"] for r in rows}
        missing = [p for p in ("QB", "RB", "WR", "TE") if p not in have]
        if missing:
            record(sec, "position mix on players with stats", "WARN",
                   "missing %s | %s" % ("/".join(missing), mix))
        else:
            record(sec, "position mix on players with stats", "PASS", mix)

    # ---- headshots ---------------------------------------------------------
    @guard(sec, "headshots on players with stats")
    def _():
        col = next((c for c in ("headshot_url", "headshot", "image_url") if c in cols), None)
        if not col:
            record(sec, "headshots on players with stats", "SKIP", "no headshot column")
            return
        row = query_one("""
            SELECT count(*) AS total,
                   count(p.%s) AS withpic
            FROM (SELECT DISTINCT ps.player_id FROM player_seasons ps) d
            JOIN players p ON p.id = d.player_id
            JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL'
        """ % col)
        total = row["total"] or 0
        withpic = row["withpic"] or 0
        pct = (100.0 * withpic / total) if total else 0.0
        detail = "%s of %s (%.0f%%)" % (withpic, total, pct)
        # Comparison cards look broken without a face on both sides.
        record(sec, "headshots on players with stats",
               "PASS" if pct >= 80 else ("WARN" if pct > 0 else "FAIL"), detail)

    # ---- deepest histories (sanity: are the big names in?) -----------------
    @guard(sec, "marquee QBs have multi-season history")
    def _():
        want = ["Patrick Mahomes", "Josh Allen", "Lamar Jackson", "Joe Burrow",
                "Tom Brady", "Peyton Manning", "Aaron Rodgers", "Mike Vick"]
        rows = query("""
            SELECT p.full_name, count(*) AS seasons
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL' AND p.full_name = ANY(%s)
            GROUP BY p.full_name
        """, (want,))
        got = {r["full_name"]: r["seasons"] for r in rows}
        missing = [w for w in want if w not in got]
        detail = ", ".join("%s:%s" % (k, v) for k, v in sorted(got.items()))
        if missing:
            record(sec, "marquee QBs have multi-season history", "FAIL",
                   "missing from DB: %s | present: %s" % (", ".join(missing), detail))
        else:
            record(sec, "marquee QBs have multi-season history", "PASS", detail)

    # ---- duplicate names ---------------------------------------------------
    @guard(sec, "duplicate-name collisions")
    def _():
        rows = query("""
            SELECT p.full_name, count(*) AS n
            FROM players p JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL'
            GROUP BY p.full_name HAVING count(*) > 1
            ORDER BY n DESC LIMIT 5
        """)
        if not rows:
            record(sec, "duplicate-name collisions", "PASS", "no duplicates")
            return
        top = ", ".join("%s x%s" % (r["full_name"], r["n"]) for r in rows)
        record(sec, "duplicate-name collisions", "WARN",
               "%s names collide; resolution must order by season count -- %s" % (len(rows), top))

    # ---- empty stat blobs --------------------------------------------------
    @guard(sec, "no empty stat blobs")
    def _():
        row = query_one("""
            SELECT count(*) AS n FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            JOIN leagues l ON l.id = p.league_id
            WHERE l.code = 'NFL' AND (ps.stats IS NULL OR ps.stats::text IN ('{}', 'null'))
        """)
        n = row["n"] if row else 0
        record(sec, "no empty stat blobs", "PASS" if n == 0 else "FAIL",
               "%s rows with no stats payload" % n)


# ============================================================================
# SECTION 2 -- NAME RESOLUTION
# ============================================================================

ACTIVE_CASES = [
    ("Patrick Mahomes", "QB"),
    ("Josh Allen", "QB"),
    ("Lamar Jackson", "QB"),
    ("Joe Burrow", "QB"),
    ("Jalen Hurts", "QB"),
    ("Saquon Barkley", "RB"),
    ("Derrick Henry", "RB"),
    ("Christian McCaffrey", "RB"),
    ("Ja'Marr Chase", "WR"),
    ("Justin Jefferson", "WR"),
    ("Tyreek Hill", "WR"),
    ("Travis Kelce", "TE"),
    ("Myles Garrett", "DE"),
    ("Micah Parsons", "LB"),
]

DEBUT_CASES = ["Cam Ward", "Travis Hunter", "Ashton Jeanty", "Brock Bowers", "Malik Nabers"]
ALIAS_CASES = [("Michael Vick", "Vick")]
GAP_CASES = ["Jerry Rice", "Barry Sanders", "Walter Payton", "Joe Montana"]


def section_lookup():
    banner("SECTION 2 / NAME RESOLUTION  (does a typed name reach the right player)")
    sec = "lookup"

    try:
        from app.player_search import resolve
    except Exception as exc:
        record(sec, "import app.player_search", "SKIP", "cannot import: %s" % exc)
        return

    def block_for(name):
        try:
            return resolve(name) or ""
        except Exception as exc:
            return "__ERROR__ %s" % exc

    # ---- active players ----------------------------------------------------
    hits = 0
    for name, _pos in ACTIVE_CASES:
        b = block_for(name)
        if b.startswith("__ERROR__"):
            record(sec, "resolve %s" % name, "FAIL", b)
        elif not b.strip():
            record(sec, "resolve %s" % name, "FAIL", "no stat block returned")
        elif "NFL" not in b:
            record(sec, "resolve %s" % name, "FAIL", "resolved to a non-NFL league")
        else:
            hits += 1
            record(sec, "resolve %s" % name, "PASS", "%s chars" % len(b))
    record(sec, "active-player hit rate", "PASS" if hits == len(ACTIVE_CASES) else "WARN",
           "%s/%s resolved" % (hits, len(ACTIVE_CASES)))

    # ---- duplicate names must pick the famous one --------------------------
    @guard(sec, "Josh Allen resolves to the QB")
    def _():
        from app.player_db import find_players
        rows = find_players("Josh Allen") or []
        if not rows:
            record(sec, "Josh Allen resolves to the QB", "WARN", "not in DB, ESPN fallback only")
            return
        first = rows[0]
        pos = (first.get("position") or "").upper() if isinstance(first, dict) else ""
        detail = "first match position=%r of %s candidates" % (pos, len(rows))
        record(sec, "Josh Allen resolves to the QB",
               "PASS" if pos == "QB" else "FAIL", detail)

    @guard(sec, "Lamar Jackson resolves to the QB")
    def _():
        from app.player_db import find_players
        rows = find_players("Lamar Jackson") or []
        if not rows:
            record(sec, "Lamar Jackson resolves to the QB", "WARN", "not in DB")
            return
        first = rows[0]
        pos = (first.get("position") or "").upper() if isinstance(first, dict) else ""
        record(sec, "Lamar Jackson resolves to the QB",
               "PASS" if pos == "QB" else "FAIL",
               "first match position=%r of %s" % (pos, len(rows)))

    # ---- aliases -----------------------------------------------------------
    for typed, expect_fragment in ALIAS_CASES:
        @guard(sec, "alias %s" % typed)
        def _(typed=typed, expect_fragment=expect_fragment):
            from app.aliases import resolve_alias
            canon = resolve_alias(typed)
            b = block_for(typed)
            ok = expect_fragment.lower() in (b or "").lower()
            record(sec, "alias %s" % typed, "PASS" if ok else "FAIL",
                   "resolve_alias -> %r, block mentions target: %s" % (canon, ok))

    # ---- 2025 debuts: the probe-year weakness ------------------------------
    debut_hits = 0
    for name in DEBUT_CASES:
        b = block_for(name)
        if b.strip() and not b.startswith("__ERROR__"):
            debut_hits += 1
            record(sec, "recent debut %s" % name, "PASS", "%s chars" % len(b))
        else:
            record(sec, "recent debut %s" % name, "FAIL",
                   "no data -- lookup probe years likely miss a first-year player")
    record(sec, "recent-debut hit rate",
           "PASS" if debut_hits == len(DEBUT_CASES) else "FAIL",
           "%s/%s resolved" % (debut_hits, len(DEBUT_CASES)))

    # ---- known source gaps: expected to be thin, not broken ----------------
    for name in GAP_CASES:
        b = block_for(name)
        if b.startswith("__ERROR__"):
            record(sec, "pre-2002 %s" % name, "FAIL", b)
        elif not b.strip():
            record(sec, "pre-2002 %s" % name, "WARN",
                   "no data -- ESPN has no pre-2002 NFL stats; needs another source")
        else:
            record(sec, "pre-2002 %s" % name, "WARN",
                   "partial data only (%s chars) -- career totals will understate" % len(b))

    # ---- name extraction from a real question ------------------------------
    @guard(sec, "extract_names on a comparison question")
    def _():
        from app.players import extract_names
        q = "Compare Lamar Jackson and Josh Allen career statistics"
        names = extract_names(q) or []
        ok = any("Lamar" in n for n in names) and any("Allen" in n for n in names)
        record(sec, "extract_names on a comparison question",
               "PASS" if ok else "FAIL", "got %r" % (names,))

    @guard(sec, "extract_names drops stopwords")
    def _():
        from app.players import extract_names
        names = extract_names("Career Statistics Comparison for Patrick Mahomes") or []
        junk = [n for n in names if n.split()[0] in
                ("Career", "Statistics", "Comparison", "Compare", "Versus")]
        record(sec, "extract_names drops stopwords",
               "PASS" if not junk else "FAIL", "got %r" % (names,))


# ============================================================================
# SECTION 3 -- COMPARISON CARDS
# ============================================================================

GOOD_PAIRS = [
    ("Lamar Jackson", "Josh Allen"),
    ("Patrick Mahomes", "Joe Burrow"),
    ("Tom Brady", "Peyton Manning"),
    ("Derrick Henry", "Saquon Barkley"),
    ("Justin Jefferson", "Ja'Marr Chase"),
    ("Mike Vick", "Lamar Jackson"),
]

FALLBACK_PAIRS = [
    ("Lamar Jackson", "Derrick Henry", "cross-position (QB vs RB)"),
    ("Lamar Jackson", "LeBron James", "cross-league (NFL vs NBA)"),
    ("Patrick Mahomes", "Shohei Ohtani", "cross-league (NFL vs MLB)"),
]


def section_compare():
    banner("SECTION 3 / COMPARISON CARDS  (the side-by-side product surface)")
    sec = "compare"

    try:
        import app.compare as C
    except Exception as exc:
        record(sec, "import app.compare", "SKIP", "cannot import: %s" % exc)
        return

    fname, build = find_callable(C, [
        "build_comparison", "compare_players", "build_compare",
        "build_card", "get_comparison", "compare",
    ])
    if not build:
        record(sec, "locate comparison entry point", "FAIL",
               "no known builder found; module exports: %s"
               % ", ".join(n for n in dir(C) if not n.startswith("_")))
        return
    record(sec, "locate comparison entry point", "PASS", "using %s()" % fname)

    def call(a, b):
        try:
            return build(a, b), None
        except TypeError:
            try:
                return build([a, b]), None
            except Exception as exc:
                return None, exc
        except Exception as exc:
            return None, exc

    def rows_of(card):
        """Pull the stat rows out of whatever shape the card uses."""
        if isinstance(card, dict):
            for k in ("rows", "stats", "lines", "metrics"):
                v = card.get(k)
                if isinstance(v, list):
                    return v, k
        if isinstance(card, list):
            return card, "(list)"
        return None, None

    # ---- pairs that must produce a card -----------------------------------
    for a, b in GOOD_PAIRS:
        label = "card: %s vs %s" % (a, b)
        card, exc = call(a, b)
        if exc:
            record(sec, label, "FAIL", "exception: %s" % exc)
            continue
        if card is None:
            record(sec, label, "FAIL", "returned None -- app falls back to prose")
            continue

        rows, key = rows_of(card)
        if rows is None:
            record(sec, label, "WARN",
                   "card built but row list not found; keys=%s"
                   % (list(card.keys()) if isinstance(card, dict) else type(card).__name__))
            continue
        if len(rows) < 5:
            record(sec, label, "WARN", "only %s stat rows (thin card)" % len(rows))
            continue

        # no null values on either side
        nulls = []
        wins_a = wins_b = ties = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            va = r.get("a", r.get("value_a"))
            vb = r.get("b", r.get("value_b"))
            if va in (None, "") or vb in (None, ""):
                nulls.append(r.get("label", "?"))
            w = r.get("winner")
            if w == "a":
                wins_a += 1
            elif w == "b":
                wins_b += 1
            else:
                ties += 1

        problems = []
        if nulls:
            problems.append("null values in %s" % ", ".join(nulls[:4]))
        if wins_a + wins_b > len(rows):
            problems.append("win count %s exceeds %s rows" % (wins_a + wins_b, len(rows)))

        detail = "%s rows (%s key), A:%s B:%s tie:%s" % (len(rows), key, wins_a, wins_b, ties)
        if problems:
            record(sec, label, "FAIL", detail + " -- " + "; ".join(problems))
        else:
            record(sec, label, "PASS", detail)

    # ---- pairs that must NOT produce a card -------------------------------
    for a, b, why in FALLBACK_PAIRS:
        label = "falls back to prose: %s vs %s" % (a, b)
        card, exc = call(a, b)
        if exc:
            record(sec, label, "FAIL", "exception instead of clean None: %s" % exc)
        elif card is None:
            record(sec, label, "PASS", why)
        else:
            record(sec, label, "FAIL",
                   "built a card for %s -- the comparison is meaningless to a user" % why)

    # ---- inverted stats: fewer interceptions should win -------------------
    @guard(sec, "lower-is-better stats score correctly")
    def _():
        card, exc = call("Lamar Jackson", "Josh Allen")
        if exc or card is None:
            record(sec, "lower-is-better stats score correctly", "SKIP",
                   "no card to inspect")
            return
        rows, _k = rows_of(card)
        if not rows:
            record(sec, "lower-is-better stats score correctly", "SKIP", "no rows")
            return
        inv = [r for r in rows if isinstance(r, dict)
               and any(t in str(r.get("label", "")).lower()
                       for t in ("int", "sack", "fumble", "turnover"))]
        if not inv:
            record(sec, "lower-is-better stats score correctly", "WARN",
                   "no inverted stat present on the card to verify")
            return
        bad = []
        for r in inv:
            va, vb = r.get("a", r.get("value_a")), r.get("b", r.get("value_b"))
            w = r.get("winner")
            try:
                fa, fb = float(va), float(vb)
            except (TypeError, ValueError):
                continue
            if fa == fb:
                if w is not None:
                    bad.append("%s: equal values but winner=%s" % (r.get("label"), w))
            else:
                expect = "a" if fa < fb else "b"
                if w != expect:
                    bad.append("%s: %s vs %s -> winner=%s, expected %s"
                               % (r.get("label"), va, vb, w, expect))
        record(sec, "lower-is-better stats score correctly",
               "PASS" if not bad else "FAIL",
               "checked %s inverted rows%s" % (len(inv), "" if not bad else " -- " + "; ".join(bad)))

    # ---- the API route the front end actually calls ------------------------
    @guard(sec, "/api/compare returns a card")
    def _():
        from app import create_app
        app = create_app()
        with app.test_client() as cl:
            for payload in ({"a": "Lamar Jackson", "b": "Josh Allen"},
                            {"player_a": "Lamar Jackson", "player_b": "Josh Allen"},
                            {"names": ["Lamar Jackson", "Josh Allen"]}):
                r = cl.post("/api/compare", json=payload)
                if r.status_code == 200:
                    data = r.get_json(silent=True) or {}
                    ok = bool(data) and data.get("comparison") is not None or bool(data)
                    record(sec, "/api/compare returns a card",
                           "PASS" if ok else "FAIL",
                           "200 with payload keys %s" % list(payload.keys()))
                    return
            record(sec, "/api/compare returns a card", "FAIL",
                   "no accepted payload shape (last status %s)" % r.status_code)


# ============================================================================
# SECTION 4 -- LIVE SCORES
# ============================================================================

def section_live():
    banner("SECTION 4 / LIVE SCORES  (today's NFL games on the ticker)")
    sec = "live"

    try:
        import app.live as L
    except Exception as exc:
        record(sec, "import app.live", "SKIP", "cannot import: %s" % exc)
        return

    # ---- clock sanity: a drifted VM clock silently empties the ticker ------
    @guard(sec, "system clock is plausible")
    def _():
        import urllib.request
        try:
            with urllib.request.urlopen("https://www.espn.com", timeout=10) as r:
                hdr = r.headers.get("Date")
        except Exception as exc:
            record(sec, "system clock is plausible", "SKIP", "no network: %s" % exc)
            return
        if not hdr:
            record(sec, "system clock is plausible", "SKIP", "no Date header")
            return
        from email.utils import parsedate_to_datetime
        remote = parsedate_to_datetime(hdr).replace(tzinfo=None)
        local = datetime.utcnow()
        skew = abs((remote - local).total_seconds())
        detail = "local UTC %s, server UTC %s, skew %.0fs" % (
            local.strftime("%Y-%m-%d %H:%M"), remote.strftime("%Y-%m-%d %H:%M"), skew)
        if skew > 3600:
            record(sec, "system clock is plausible", "FAIL",
                   detail + " -- date filters will drop real games; run: sudo date -s ...")
        else:
            record(sec, "system clock is plausible", "PASS", detail)

    fname, fetch = find_callable(L, ["get_espn_games", "get_games", "fetch_games"])
    if not fetch:
        record(sec, "locate scoreboard fetcher", "FAIL",
               "module exports: %s" % ", ".join(n for n in dir(L) if not n.startswith("_")))
        return
    record(sec, "locate scoreboard fetcher", "PASS", "using %s()" % fname)

    games = []

    @guard(sec, "NFL scoreboard fetch")
    def _():
        nonlocal_games = fetch("football/nfl")
        games.extend(nonlocal_games or [])
        if not games:
            record(sec, "NFL scoreboard fetch", "WARN",
                   "zero games returned -- fine on an off day, a defect on game day")
        else:
            record(sec, "NFL scoreboard fetch", "PASS", "%s games" % len(games))

    # ---- field completeness ------------------------------------------------
    @guard(sec, "game records are fully populated")
    def _():
        if not games:
            record(sec, "game records are fully populated", "SKIP", "no games today")
            return
        required = ["away_abbr", "home_abbr", "status"]
        missing = {}
        for g in games:
            for k in required:
                if not g.get(k):
                    missing.setdefault(k, 0)
                    missing[k] += 1
        if missing:
            record(sec, "game records are fully populated", "FAIL",
                   "blank fields: %s" % missing)
        else:
            sample = games[0]
            record(sec, "game records are fully populated", "PASS",
                   "%s @ %s -- %s" % (sample.get("away_abbr"), sample.get("home_abbr"),
                                      sample.get("status")))

    # ---- rolling window ----------------------------------------------------
    @guard(sec, "is_today rolling window")
    def _():
        is_today = getattr(L, "is_today", None)
        if not callable(is_today):
            record(sec, "is_today rolling window", "SKIP", "function not exported")
            return
        now = datetime.utcnow()

        def stamp(hours):
            from datetime import timedelta
            return {"date": (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M") + "Z"}

        checks = [
            ("finished 6h ago", stamp(-6), True),
            ("kicking off in 3h", stamp(3), True),
            ("next week", stamp(24 * 7), False),
            ("three days ago", stamp(-72), False),
        ]
        bad = [n for n, g, want in checks if bool(is_today(g)) != want]
        record(sec, "is_today rolling window",
               "PASS" if not bad else "FAIL",
               "all 4 window cases correct" if not bad else "wrong for: %s" % ", ".join(bad))

    # ---- the trigger phrases users actually type --------------------------
    @guard(sec, "live-score trigger phrases")
    def _():
        gname, gfn = find_callable(L, ["get_todays_games", "todays_games", "live_context"])
        if not gfn:
            record(sec, "live-score trigger phrases", "SKIP", "no trigger function exported")
            return
        phrases = [
            "What NFL games are on today?",
            "Who is playing in the NFL tonight?",
            "NFL scores",
            "Any football games today?",
        ]
        empty = []
        for p in phrases:
            try:
                out = gfn(p)
            except TypeError:
                out = gfn()
            if not out:
                empty.append(p)
        if not empty:
            record(sec, "live-score trigger phrases", "PASS",
                   "all %s phrases returned context (via %s)" % (len(phrases), gname))
        elif len(empty) == len(phrases) and not games:
            record(sec, "live-score trigger phrases", "WARN",
                   "no context, but no NFL games on the board today either")
        else:
            record(sec, "live-score trigger phrases", "FAIL",
                   "no context for: %s" % "; ".join(empty))


# ============================================================================
# SECTION 5 -- RAG ANSWER QUALITY  (costs API credits)
# ============================================================================

BANNED_SOURCES = [
    "espn.com", "espn ", "nfl.com", "statmuse", "pro-football-reference",
    "sports-reference", "pff.com", "pff ", "nfl network", "google",
    "wikipedia", "the athletic",
]

BANNED_PHRASES = [
    "i don't have access", "i do not have access", "knowledge cutoff",
    "you can find", "you could check", "refer to", "visit ",
    "check out", "i'm unable to", "as an ai",
]

FILLER_OPENERS = [
    "great question", "let me break", "i need to be", "that's a good question",
    "sure,", "certainly", "happy to help", "it depends",
]

RAG_CASES = [
    ("Compare Lamar Jackson and Josh Allen career statistics", 250),
    ("How many passing yards did Patrick Mahomes have last season?", 90),
    ("Is Derrick Henry still an elite running back?", 200),
    ("Who had more receiving yards, Justin Jefferson or Ja'Marr Chase?", 120),
    ("What were Jerry Rice's career receiving numbers?", 200),
    ("What NFL games are on today?", 160),
]


def section_rag():
    banner("SECTION 5 / ANSWER QUALITY  (Claude API -- this section costs credits)")
    sec = "rag"

    try:
        from app.rag import generate_response
    except Exception as exc:
        record(sec, "import app.rag", "SKIP", "cannot import: %s" % exc)
        return

    for question, max_words in RAG_CASES:
        short = question if len(question) < 52 else question[:49] + "..."
        t0 = time.time()
        try:
            answer = generate_response(question) or ""
        except Exception as exc:
            record(sec, "answer: %s" % short, "FAIL", "exception: %s" % exc)
            continue
        elapsed = time.time() - t0
        low = answer.lower()
        words = len(answer.split())

        problems = []
        hit = [s for s in BANNED_SOURCES if s in low]
        if hit:
            problems.append("sends users away: %s" % ", ".join(hit[:3]))
        hit = [s for s in BANNED_PHRASES if s in low]
        if hit:
            problems.append("hedging: %s" % ", ".join(hit[:3]))
        hit = [s for s in FILLER_OPENERS if low.lstrip("*# ").startswith(s)]
        if hit:
            problems.append("filler opener: %s" % hit[0])
        if words > max_words:
            problems.append("%s words over the %s limit" % (words, max_words))
        if answer.count("##") > 2:
            problems.append("%s headers (too structured for a chat answer)" % answer.count("##"))
        if not answer.strip():
            problems.append("empty answer")

        detail = "%s words, %.1fs" % (words, elapsed)
        if problems:
            record(sec, "answer: %s" % short, "FAIL", detail + " -- " + "; ".join(problems))
        else:
            record(sec, "answer: %s" % short, "PASS", detail)

    # ---- did retrieval actually fire? -------------------------------------
    @guard(sec, "retrieval supplies verified data")
    def _():
        from app.player_search import search_players
        ctx = search_players("Compare Lamar Jackson and Josh Allen") or ""
        if not ctx.strip():
            record(sec, "retrieval supplies verified data", "FAIL",
                   "empty context -- the model is answering from memory, not data")
        else:
            record(sec, "retrieval supplies verified data", "PASS",
                   "%s chars of context retrieved" % len(ctx))


# ============================================================================
# REPORT
# ============================================================================

def write_report(sections_run):
    counts = {}
    for r in RESULTS:
        counts.setdefault(r["section"], {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0})
        counts[r["section"]][r["status"]] += 1

    total = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
    for c in counts.values():
        for k in total:
            total[k] += c[k]

    lines = []
    lines.append("# Rigorlytics -- NFL UAT Report")
    lines.append("")
    lines.append("Run: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("Sections: %s" % ", ".join(sections_run))
    lines.append("Duration: %.1fs" % (time.time() - START))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Section | Pass | Fail | Warn | Skip |")
    lines.append("|---|---|---|---|---|")
    for s in SECTION_ORDER:
        if s in counts:
            c = counts[s]
            lines.append("| %s | %s | %s | %s | %s |" % (s, c["PASS"], c["FAIL"], c["WARN"], c["SKIP"]))
    lines.append("| **total** | **%s** | **%s** | **%s** | **%s** |"
                 % (total["PASS"], total["FAIL"], total["WARN"], total["SKIP"]))
    lines.append("")

    fails = [r for r in RESULTS if r["status"] == "FAIL"]
    if fails:
        lines.append("## Defects to fix (%s)" % len(fails))
        lines.append("")
        for r in fails:
            lines.append("- **[%s] %s** -- %s" % (r["section"], r["name"], r["detail"]))
        lines.append("")

    warns = [r for r in RESULTS if r["status"] == "WARN"]
    if warns:
        lines.append("## Known limitations (%s)" % len(warns))
        lines.append("")
        for r in warns:
            lines.append("- *[%s] %s* -- %s" % (r["section"], r["name"], r["detail"]))
        lines.append("")

    lines.append("## Full results")
    lines.append("")
    lines.append("| Section | Check | Status | Detail |")
    lines.append("|---|---|---|---|")
    for r in RESULTS:
        detail = r["detail"].replace("|", "/").replace("\n", " ")
        lines.append("| %s | %s | %s | %s |" % (r["section"], r["name"], r["status"], detail))
    lines.append("")

    out = "uat_nfl_report.md"
    with open(out, "w") as f:
        f.write("\n".join(lines))
    return out, total


def main():
    arg = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()

    runners = {
        "data": section_data,
        "lookup": section_lookup,
        "compare": section_compare,
        "live": section_live,
        "rag": section_rag,
    }

    if arg == "all":
        chosen = ["data", "lookup", "compare", "live"]
    elif arg in ("all+rag", "full"):
        chosen = SECTION_ORDER
    elif arg in runners:
        chosen = [arg]
    else:
        print(__doc__)
        return 2

    print("Rigorlytics NFL UAT -- sections: %s" % ", ".join(chosen))
    for s in chosen:
        runners[s]()

    path, total = write_report(chosen)

    banner("RESULT")
    print("  pass %s   fail %s   warn %s   skip %s"
          % (total["PASS"], total["FAIL"], total["WARN"], total["SKIP"]))
    print("  report written to %s" % path)
    return 1 if total["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
