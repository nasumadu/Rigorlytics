#!/usr/bin/env python3
"""
Rigorlytics - pre-1999 NFL season leaders from Wikipedia.

nflverse starts at 1999. Everything earlier is behind Pro-Football-Reference's
terms or a paid feed, except one clean source: Wikipedia's annual leaders lists,
which run back to 1932 and are CC BY-SA - free to use with attribution.

The trade-off is honest and must stay visible: these are LEADERS, not rosters.
Rows land with source='wikipedia_leaders' so the valuation engine can refuse to
compute percentiles or comparable sets against a cohort of six people. Knowing
who led the league in 1972 is useful; pretending to rank a 1972 player against
his peers when we hold five of them is the failure this system exists to avoid.

    python scripts_ingest_wiki_leaders.py --probe passing_yards
    python scripts_ingest_wiki_leaders.py --list
    python scripts_ingest_wiki_leaders.py --years 1966-1998 --dry-run
    python scripts_ingest_wiki_leaders.py --years 1966-1998 --write
    python scripts_ingest_wiki_leaders.py --years 1960-1998 --include-afl --write

Attribution: data from Wikipedia, CC BY-SA 4.0.
"""

import os, sys, re, json, time, argparse, unicodedata, urllib.parse, urllib.request
from html.parser import HTMLParser

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.getcwd())
from app.db import get_conn

API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net; contact via site)"}
SOURCE = "wikipedia_leaders"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# key -> (candidate page titles, stat column we store it as, header words to find,
#         position hint)
CATEGORIES = {
    "passing_yards": (
        ["List of National Football League annual passing yards leaders"],
        "passing.passingYards", ["yds", "yards"], "QB"),
    "passing_touchdowns": (
        ["List of National Football League annual passing touchdowns leaders"],
        "passing.passingTouchdowns", ["td", "tds", "touchdowns"], "QB"),
    "rushing_yards": (
        ["List of National Football League annual rushing yards leaders"],
        "rushing.rushingYards", ["yds", "yards"], "RB"),
    "rushing_touchdowns": (
        ["List of National Football League annual rushing touchdowns leaders"],
        "rushing.rushingTouchdowns", ["td", "tds", "touchdowns"], "RB"),
    "receiving_yards": (
        ["List of National Football League annual receiving yards leaders"],
        "receiving.receivingYards", ["yds", "yards"], "WR"),
    "receptions": (
        ["List of National Football League annual receptions leaders"],
        "receiving.receptions", ["rec", "receptions", "no."], "WR"),
    "receiving_touchdowns": (
        ["List of National Football League annual receiving touchdowns leaders"],
        "receiving.receivingTouchdowns", ["td", "tds", "touchdowns"], "WR"),
    "sacks": (
        ["List of National Football League annual sacks leaders"],
        "defensive.sacks", ["sacks", "sk"], "DL"),
    "interceptions": (
        ["List of National Football League annual interceptions leaders"],
        "defensiveInterceptions.interceptions", ["int", "ints", "interceptions"], "DB"),
    "scoring": (
        ["List of National Football League annual scoring leaders"],
        "scoring.totalPoints", ["pts", "points"], "ST"),
    "punting": (
        ["List of National Football League annual punting leaders"],
        "nflverse.punting_average", ["avg", "average"], "ST"),
}

SEASON_RE = re.compile(r"(19\d{2}|20\d{2})")
NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


# ------------------------------------------------------------------ wiki

def api(params):
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def page_html(title):
    d = api({"action": "parse", "page": title, "prop": "text", "redirects": "1"})
    if "error" in d:
        return None, d["error"].get("info", "not found")
    return d["parse"]["text"], None


class TableGrab(HTMLParser):
    """Pull wikitable rows out of rendered HTML, keeping the heading above each.

    Wikitext parsing is a swamp; rendered HTML is regular. We only need cell
    text, so a small state machine beats pulling in a dependency.
    """

    def __init__(self):
        HTMLParser.__init__(self)
        self.tables, self.heading = [], ""
        self._cur = self._row = self._cell = None
        self._depth = 0
        self._in_head = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h2", "h3"):
            self._in_head = True
            self._headbuf = []
        elif tag == "table":
            self._depth += 1
            if self._depth == 1 and "wikitable" in (a.get("class") or ""):
                self._cur = {"heading": self.heading, "rows": []}
        elif tag == "tr" and self._cur is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag in ("sup", "style", "script"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("h2", "h3"):
            self._in_head = False
            self.heading = " ".join("".join(self._headbuf).split())
        elif tag == "table":
            if self._depth == 1 and self._cur is not None:
                self.tables.append(self._cur)
                self._cur = None
            self._depth = max(0, self._depth - 1)
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._cur["rows"].append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag in ("sup", "style", "script"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_head:
            self._headbuf.append(data)
        elif self._cell is not None:
            self._cell.append(data)


def tables_for(title):
    html, err = page_html(title)
    if err:
        return None, err
    g = TableGrab()
    g.feed(html)
    return g.tables, None


# ------------------------------------------------------------------ parsing

def norm_name(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("-", " ").replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(p for p in s.split() if p and p not in SUFFIXES)


def clean(cell):
    """Drop footnote markers, daggers and bracketed notes."""
    c = re.sub(r"\[[^\]]*\]", "", cell or "")
    c = c.replace("†", "").replace("*", "").replace("‡", "")
    return c.strip()


def num(cell):
    m = NUM_RE.search(clean(cell).replace(",", "") or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def column_map(header, value_words):
    """Locate season / player / value / team / games columns by header text."""
    idx = {}
    for i, h in enumerate(header):
        h = clean(h).lower()
        if not h:
            continue
        if "season" in h or h in ("year",):
            idx.setdefault("season", i)
        elif ("leader" in h or "player" in h or "name" in h
              or "winner" in h or "champion" in h):
            idx.setdefault("player", i)
        elif "team" in h or "club" in h:
            idx.setdefault("team", i)
        elif h in ("gp", "g", "games") or "games" in h:
            idx.setdefault("games", i)
        elif any(w == h or w in h for w in value_words):
            idx.setdefault("value", i)
    return idx


def repair_columns(idx, sample):
    """Trust the data over the header.

    Wikipedia is inconsistent: the rushing page labels its player column
    "Winner", and the receiving page labels its SEASON column "Leader". A header
    map alone silently drops whole pages, so verify each choice against a real
    data row and re-derive anything that does not hold up.
    """
    def is_year(cell):
        c = clean(cell)
        return bool(re.fullmatch(r"(19|20)\d{2}", c[:4])) and len(c) <= 6

    if ("season" not in idx or idx["season"] >= len(sample)
            or not is_year(sample[idx["season"]])):
        for i, cell in enumerate(sample):
            if is_year(cell):
                idx["season"] = i
                break

    if "player" not in idx or idx.get("player") == idx.get("season"):
        for i, cell in enumerate(sample):
            if i == idx.get("season") or i == idx.get("team"):
                continue
            t = clean(cell)
            if t and any(ch.isalpha() for ch in t) and num(t) is None:
                idx["player"] = i
                break

    if "value" not in idx or idx.get("value") in (idx.get("season"), idx.get("player")):
        for i, cell in enumerate(sample):
            if i in (idx.get("season"), idx.get("player"), idx.get("team")):
                continue
            v = num(cell)
            if v is not None and v > 25:      # a games-played column would be smaller
                idx["value"] = i
                break
    return idx


def rows_from_page(title, value_words, include_afl=False):
    tabs, err = tables_for(title)
    if err:
        return None, err
    out = []
    for t in tabs:
        rows = t["rows"]
        if len(rows) < 3:
            continue
        header = rows[0]
        idx = column_map(header, value_words)
        idx = repair_columns(idx, rows[1])
        if "season" not in idx or "player" not in idx or "value" not in idx:
            continue
        league = "NFL"
        head = (t["heading"] or "").upper()
        if "AFL" in head and "NFL" not in head:
            league = "AFL"
        elif "AAFC" in head:
            league = "AAFC"
        if league != "NFL" and not include_afl:
            continue
        for r in rows[1:]:
            if len(r) <= max(idx.values()):
                continue
            m = SEASON_RE.search(clean(r[idx["season"]]))
            if not m:
                continue
            name = clean(r[idx["player"]])
            val = num(r[idx["value"]])
            if not name or val is None:
                continue
            out.append(dict(
                year=int(m.group(1)), player=name, value=val, league=league,
                team=clean(r[idx["team"]]) if "team" in idx and len(r) > idx["team"] else None,
                games=num(r[idx["games"]]) if "games" in idx and len(r) > idx["games"] else None,
            ))
    return out, None


# ------------------------------------------------------------------ db

def league_id(cur):
    cur.execute("SELECT id FROM leagues WHERE code='NFL'")
    r = cur.fetchone()
    return dict(r)["id"] if r else None


def season_id(cur, lid, year):
    cur.execute("""SELECT id FROM seasons WHERE league_id=%s AND year=%s
                   AND season_type='regular'""", (lid, year))
    r = cur.fetchone()
    if r:
        return dict(r)["id"]
    cur.execute("""INSERT INTO seasons (league_id, year, season_type)
                   VALUES (%s,%s,'regular') RETURNING id""", (lid, year))
    return dict(cur.fetchone())["id"]


def find_or_make_player(cur, lid, name, pos, cache):
    n = norm_name(name)
    if not n:
        return None
    if n in cache:
        return cache[n]
    cur.execute("""SELECT id FROM players WHERE league_id=%s
                   AND lower(full_name)=lower(%s) LIMIT 1""", (lid, name))
    r = cur.fetchone()
    if r:
        cache[n] = dict(r)["id"]
        return cache[n]
    cur.execute("""INSERT INTO players (league_id, external_id, full_name, position, active)
                   VALUES (%s,%s,%s,%s,FALSE) RETURNING id""",
                (lid, "wiki:" + n.replace(" ", "_"), name, pos))
    cache[n] = dict(cur.fetchone())["id"]
    return cache[n]


def upsert(cur, pid, sid, stat_key, value, games):
    """Merge into the season row, preserving any stats already there."""
    cur.execute("""SELECT id, stats, source FROM player_seasons
                   WHERE player_id=%s AND season_id=%s""", (pid, sid))
    ex = cur.fetchone()
    if ex:
        ex = dict(ex)
        stats = ex["stats"] or {}
        if isinstance(stats, str):
            try:
                stats = json.loads(stats)
            except ValueError:
                stats = {}
        # Never overwrite a real ingested figure with a Wikipedia one.
        if ex["source"] and ex["source"] not in (SOURCE,):
            return "KEPT"
        stats[stat_key] = value
        if games:
            stats["general.gamesPlayed"] = games
        cur.execute("""UPDATE player_seasons SET stats=%s::jsonb, games_played=%s,
                       source=%s, updated_at=now() WHERE id=%s""",
                    (json.dumps(stats), int(games) if games else None, SOURCE, ex["id"]))
        return "UPD"
    stats = {stat_key: value}
    if games:
        stats["general.gamesPlayed"] = games
    cur.execute("""INSERT INTO player_seasons
        (player_id, season_id, games_played, stats, source, updated_at)
        VALUES (%s,%s,%s,%s::jsonb,%s,now())""",
        (pid, sid, int(games) if games else None, json.dumps(stats), SOURCE))
    return "INS"


# ------------------------------------------------------------------ main

def parse_years(spec):
    if not spec:
        return None
    lo, hi = (spec.split("-") + [spec])[:2]
    return int(lo), int(hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1966-1998")
    ap.add_argument("--categories", default="all")
    ap.add_argument("--include-afl", action="store_true")
    ap.add_argument("--probe", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.list:
        for k, (titles, key, words, pos) in CATEGORIES.items():
            print("  %-22s -> %-42s %s" % (k, key, titles[0]))
        return

    if a.probe:
        titles, key, words, pos = CATEGORIES[a.probe]
        for t in titles:
            rows, err = rows_from_page(t, words, a.include_afl)
            if err:
                print("%s -> %s" % (t, err)); continue
            print("%s -> %d rows" % (t, len(rows)))
            for r in rows[:6] + rows[-4:]:
                print("   %s  %-24s %-10s %s"
                      % (r["year"], r["player"], r["value"], r["team"] or ""))
        return

    lo, hi = parse_years(a.years)
    keys = ([k for k in CATEGORIES] if a.categories == "all"
            else [k.strip() for k in a.categories.split(",")])

    with get_conn() as c:
        cur = c.cursor()
        lid = league_id(cur)
        if lid is None:
            sys.exit("no NFL league row")
        cache = {}
        totals = dict(ins=0, upd=0, kept=0, skipped=0, pages=0)

        for k in keys:
            if k not in CATEGORIES:
                print("  unknown category %s" % k); continue
            titles, stat_key, words, pos = CATEGORIES[k]
            got = None
            for t in titles:
                rows, err = rows_from_page(t, words, a.include_afl)
                if not err and rows:
                    got = (t, rows)
                    break
            if not got:
                print("  %-22s PAGE NOT USABLE (%s)" % (k, err))
                continue
            title, rows = got
            totals["pages"] += 1
            rows = [r for r in rows if lo <= r["year"] <= hi]
            ins = upd = kept = 0
            for r in rows:
                pid = find_or_make_player(cur, lid, r["player"], pos, cache)
                if not pid:
                    totals["skipped"] += 1
                    continue
                if a.dry_run or not a.write:
                    continue
                sid = season_id(cur, lid, r["year"])
                res = upsert(cur, pid, sid, stat_key, r["value"], r["games"])
                ins += res == "INS"; upd += res == "UPD"; kept += res == "KEPT"
            if a.write and not a.dry_run:
                c.commit()
            print("  %-22s %3d rows %s->%s   inserted=%-4d updated=%-4d left-alone=%d"
                  % (k, len(rows), lo, hi, ins, upd, kept))
            totals["ins"] += ins; totals["upd"] += upd; totals["kept"] += kept
            time.sleep(0.5)          # be polite to Wikipedia

        print("\n%d pages | inserted=%d updated=%d preserved=%d%s"
              % (totals["pages"], totals["ins"], totals["upd"], totals["kept"],
                 "   (DRY RUN - nothing written)" if not a.write or a.dry_run else ""))
        if a.write and not a.dry_run:
            print("Rows carry source='%s'. Attribution: Wikipedia, CC BY-SA 4.0."
                  % SOURCE)


if __name__ == "__main__":
    main()
