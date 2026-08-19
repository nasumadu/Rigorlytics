"""
Rigorlytics - what the database actually contains.

The model has no way to know which seasons were ingested, so when asked to
compare careers it fills the gap from memory and presents the result with full
confidence. Stating the coverage explicitly turns that failure into the right
answer: "I hold NFL 2025 only" instead of a fluent recital of numbers this
system cannot stand behind.

Cheap query, cached for fifteen minutes, and it degrades to silence rather than
blocking an answer if the database is unreachable.
"""

import time

try:
    from app.db import get_conn
except ImportError:
    from db import get_conn

_CACHE = {"text": None, "at": 0.0}
TTL_SECONDS = 900


def _build():
    rows = []
    with get_conn() as c:
        cur = c.cursor()
        # Per-year counts, because a season range hides how thin the old years
        # are: NFL 2016 holds thirty players, 2025 holds nearly two thousand.
        # Saying "2002-2025" would imply a completeness we do not have.
        cur.execute("""
            SELECT l.code AS league, s.season_type AS kind, s.year AS yr,
                   count(ps.id) AS n
            FROM leagues l
            JOIN seasons s ON s.league_id = l.id
            JOIN player_seasons ps ON ps.season_id = s.id
            GROUP BY l.code, s.season_type, s.year
            ORDER BY l.code, s.season_type, s.year
        """)
        groups = {}
        for r in cur.fetchall():
            r = dict(r)
            if not r["n"]:
                continue
            groups.setdefault((r["league"], r["kind"]), {})[int(r["yr"])] = int(r["n"])

        def span(years):
            years = sorted(years)
            return (str(years[0]) if len(years) == 1
                    else "%s-%s" % (years[0], years[-1]))

        for (league, kind), years in sorted(groups.items()):
            top = max(years.values())
            full = [y for y, n in years.items() if n >= 0.5 * top]
            thin = {y: n for y, n in years.items() if n < 0.5 * top}
            part = "%s %s season: %s complete rosters (%s players)" % (
                league, kind, span(full), format(sum(years[y] for y in full), ","))
            if thin:
                part += ("; %s partial - only %d-%d players per season, a subset of "
                         "notable names rather than full rosters"
                         % (span(thin.keys()), min(thin.values()), max(thin.values())))
            rows.append(part)

        cur.execute("""SELECT l.code AS league, count(*) AS n
                       FROM contracts ct
                       JOIN players p ON p.id = ct.player_id
                       JOIN leagues l ON l.id = p.league_id
                       GROUP BY l.code ORDER BY l.code""")
        money = ["%s salaries (%s)" % (dict(r)["league"], format(dict(r)["n"], ","))
                 for r in cur.fetchall()]
        try:
            cur.execute("""SELECT l.code AS league, count(*) AS n
                           FROM player_market_profile mp
                           JOIN players p ON p.id = mp.player_id
                           JOIN leagues l ON l.id = p.league_id
                           GROUP BY l.code ORDER BY l.code""")
            money += ["%s market values (%s)" % (dict(r)["league"],
                                                 format(dict(r)["n"], ","))
                      for r in cur.fetchall()]
        except Exception:
            pass

    if not rows:
        return "DATA COVERAGE: no seasons loaded."

    out = ["DATA COVERAGE - the ONLY seasons Rigorlytics holds:"]
    out += ["  " + r for r in rows]
    if money:
        out.append("  money: " + "; ".join(money))
    out.append(
        "Any other season, any career total, and any player not covered above is "
        "NOT in this database. If a question needs data outside this list, say "
        "which seasons you actually hold and offer to work within them. Do not "
        "supply the missing figures from memory - a remembered number you cannot "
        "point to in the data is exactly what this system exists to avoid.")
    return "\n".join(out)


def coverage_line(force=False):
    now = time.time()
    if force or not _CACHE["text"] or now - _CACHE["at"] > TTL_SECONDS:
        try:
            _CACHE["text"] = _build()
            _CACHE["at"] = now
        except Exception:
            return ""
    return _CACHE["text"]


if __name__ == "__main__":
    print(coverage_line(force=True))
