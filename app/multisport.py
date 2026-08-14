"""
app/multisport.py — single source of truth for every league Rigorlytics covers.

Import this anywhere instead of hardcoding ESPN paths or position groups:

    
"""

LEAGUES = {
    # ---------------- existing pro leagues ----------------
    "nfl": {
        "label": "NFL", "full": "National Football League",
        "sport": "football", "path": "nfl", "groups": None,
        "season_style": "single", "has_contracts": True, "draws": False,
        "positions": ["QB","RB","WR","TE","OT","OG","C","DE","DT","LB","CB","S","K","P"],
        "position_groups": {"QB": ["QB"], "RB": ["RB","FB"], "WR": ["WR"], "TE": ["TE"],
                             "OL": ["OT","OG","C"], "DL": ["DE","DT"], "LB": ["LB"],
                             "DB": ["CB","S"], "ST": ["K","P"]},
    },
    "nba": {
        "label": "NBA", "full": "National Basketball Association",
        "sport": "basketball", "path": "nba", "groups": None,
        "season_style": "split", "has_contracts": True, "draws": False,
        "positions": ["G","F","C"],
        "position_groups": {"ALL": ["G","F","C","PG","SG","SF","PF"]},
    },
    "wnba": {
        "label": "WNBA", "full": "Women's National Basketball Association",
        "sport": "basketball", "path": "wnba", "groups": None,
        "season_style": "single", "has_contracts": True, "draws": False,
        "positions": ["G","F","C"],
        "position_groups": {"ALL": ["G","F","C"]},
    },
    "mlb": {
        "label": "MLB", "full": "Major League Baseball",
        "sport": "baseball", "path": "mlb", "groups": None,
        "season_style": "single", "has_contracts": True, "draws": False,
        "positions": ["SP","RP","C","1B","2B","3B","SS","LF","CF","RF","DH"],
        "position_groups": {"P": ["SP","RP","P"], "IF": ["1B","2B","3B","SS"],
                             "OF": ["LF","CF","RF","OF"], "C": ["C"], "DH": ["DH"]},
    },
    "nhl": {
        "label": "NHL", "full": "National Hockey League",
        "sport": "hockey", "path": "nhl", "groups": None,
        "season_style": "split", "has_contracts": True, "draws": False,
        "positions": ["C","LW","RW","D","G"],
        "position_groups": {"F": ["C","LW","RW"], "D": ["D"], "G": ["G"]},
    },

    # ---------------- new: college ----------------
    "cfb": {
        "label": "CFB", "full": "NCAA Football",
        "sport": "football", "path": "college-football", "groups": "80",  # FBS
        "season_style": "single", "has_contracts": False, "draws": False,
        "positions": ["QB","RB","WR","TE","OT","OG","C","DE","DT","LB","CB","S","K","P"],
        "position_groups": {"QB": ["QB"], "RB": ["RB","FB"], "WR": ["WR"], "TE": ["TE"],
                             "OL": ["OT","OG","C","OL"], "DL": ["DE","DT","DL"],
                             "LB": ["LB"], "DB": ["CB","S","DB"], "ST": ["K","P"]},
    },
    "mcbb": {
        "label": "MCBB", "full": "NCAA Men's Basketball",
        "sport": "basketball", "path": "mens-college-basketball", "groups": "50",  # D-I
        "season_style": "split", "has_contracts": False, "draws": False,
        "positions": ["G","F","C"],
        "position_groups": {"ALL": ["G","F","C"]},
    },
    "wcbb": {
        "label": "WCBB", "full": "NCAA Women's Basketball",
        "sport": "basketball", "path": "womens-college-basketball", "groups": "50",
        "season_style": "split", "has_contracts": False, "draws": False,
        "positions": ["G","F","C"],
        "position_groups": {"ALL": ["G","F","C"]},
    },

    # ---------------- new: soccer ----------------
    "epl": {
        "label": "EPL", "full": "Premier League",
        "sport": "soccer", "path": "eng.1", "groups": None,
        "season_style": "split", "has_contracts": True, "draws": True,
        "positions": ["GK","DF","MF","FW"],
        # keepers never compare to outfield players — stat sets don't overlap
        "position_groups": {"GK": ["GK","G"], "DF": ["DF","D"], "MF": ["MF","M"], "FW": ["FW","F"]},
    },
    "mls": {
        "label": "MLS", "full": "Major League Soccer",
        "sport": "soccer", "path": "usa.1", "groups": None,
        "season_style": "single", "has_contracts": True, "draws": True,
        "positions": ["GK","DF","MF","FW"],
        "position_groups": {"GK": ["GK","G"], "DF": ["DF","D"], "MF": ["MF","M"], "FW": ["FW","F"]},
    },
}

# display order for tabs / nav
ORDER = ["nfl", "cfb", "nba", "mcbb", "wcbb", "wnba", "mlb", "nhl", "epl", "mls"]

# grouping for nav menus
FAMILIES = {
    "Football":   ["nfl", "cfb"],
    "Basketball": ["nba", "mcbb", "wcbb", "wnba"],
    "Baseball":   ["mlb"],
    "Hockey":     ["nhl"],
    "Soccer":     ["epl", "mls"],
}


def league(key):
    """Look up a league by key, case-insensitively. Returns None if unknown."""
    if not key:
        return None
    return LEAGUES.get(str(key).strip().lower())


def active_keys():
    return [k for k in ORDER if k in LEAGUES]


def resolve(text):
    """Map loose user text ('premier league', 'march madness') to a league key."""
    if not text:
        return None
    t = str(text).strip().lower()
    if t in LEAGUES:
        return t
    ALIASES = {
        "college football": "cfb", "ncaaf": "cfb", "ncaa football": "cfb",
        "mens college basketball": "mcbb", "ncaam": "mcbb", "march madness": "mcbb",
        "college basketball": "mcbb", "mens basketball": "mcbb",
        "womens college basketball": "wcbb", "ncaaw": "wcbb", "womens basketball": "wcbb",
        "premier league": "epl", "epl": "epl", "english premier league": "epl",
        "major league soccer": "mls", "soccer": "mls",
        "pro football": "nfl", "pro basketball": "nba", "baseball": "mlb", "hockey": "nhl",
    }
    return ALIASES.get(t)


def position_group(league_key, position):
    """Which comparison bucket a position belongs to ('QB', 'GK', 'ALL'...)."""
    cfg = league(league_key)
    if not cfg or not position:
        return None
    p = str(position).strip().upper()
    for group, members in cfg["position_groups"].items():
        if p in members:
            return group
    return None


def comparable(league_key, pos_a, pos_b):
    """True when two positions may be compared side by side."""
    ga = position_group(league_key, pos_a)
    gb = position_group(league_key, pos_b)
    return bool(ga) and ga == gb


# ===================== live scores =====================

import json, time, urllib.parse, urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{path}/scoreboard"
UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net)"}

_CACHE = {}
_TTL = 45          # seconds; the ticker polls every 60


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _side(competitors, which):
    for c in competitors or []:
        if c.get("homeAway") == which:
            t = c.get("team") or {}
            rec = ""
            for r in (c.get("records") or []):
                if r.get("type") in (None, "total") or r.get("name") in (None, "overall", "All Splits"):
                    rec = r.get("summary") or ""
                    break
            score = c.get("score")
            return {
                "name": t.get("shortDisplayName") or t.get("displayName") or "",
                "full": t.get("displayName") or "",
                "abbr": t.get("abbreviation") or "",
                "logo": t.get("logo") or "",
                "score": str(score) if score not in (None, "") else None,
                "record": rec,
                "winner": bool(c.get("winner")),
            }
    return None


def _norm_event(ev, key, cfg):
    comps = (ev.get("competitions") or [{}])[0]
    competitors = comps.get("competitors") or []
    home = _side(competitors, "home")
    away = _side(competitors, "away")
    if not home or not away:
        return None

    st = ((ev.get("status") or {}).get("type") or {})
    state = st.get("state") or "pre"
    status = st.get("shortDetail") or st.get("detail") or ""

    # ESPN reports "0" for games that have not started - show no score at all
    if state == "pre":
        home["score"] = away["score"] = None

    # soccer can end level — never render a draw as a "winner"
    draw = False
    if cfg.get("draws") and state == "post":
        try:
            draw = home["score"] is not None and home["score"] == away["score"]
        except Exception:
            draw = False
    if draw:
        home["winner"] = away["winner"] = False

    return {
        "id": str(ev.get("id") or ""),
        "league": key,
        "league_label": cfg["label"],
        "state": state,                       # pre | in | post
        "status": status,
        "draw": draw,
        "start": ev.get("date"),
        "name": ev.get("shortName") or ev.get("name") or "",
        "home": home,
        "away": away,
    }


def scoreboard(key, date=None, use_cache=True):
    """Normalized list of games for one league. `date` as YYYYMMDD."""
    cfg = league(key)
    if not cfg:
        raise ValueError(f"unknown league: {key}")

    ck = (key, date)
    if use_cache:
        hit = _CACHE.get(ck)
        if hit and (time.time() - hit[0]) < _TTL:
            return hit[1]

    params = {}
    if cfg.get("groups"):
        params["groups"] = cfg["groups"]
    if date:
        params["dates"] = date
    url = SITE.format(sport=cfg["sport"], path=cfg["path"])
    if params:
        url += "?" + urllib.parse.urlencode(params)

    try:
        data = _get(url)
    except Exception:
        hit = _CACHE.get(ck)          # serve stale rather than break the page
        return hit[1] if hit else []

    games = []
    for ev in (data.get("events") or []):
        try:
            g = _norm_event(ev, key, cfg)
            if g:
                games.append(g)
        except Exception:
            continue

    # in-progress first, then upcoming, then finals
    order = {"in": 0, "pre": 1, "post": 2}
    games.sort(key=lambda g: (order.get(g["state"], 3), g.get("start") or ""))

    _CACHE[ck] = (time.time(), games)
    return games


def scoreboard_many(keys=None, date=None):
    """{league_key: [games]} for several leagues. Never raises on one bad league."""
    out = {}
    for k in (keys or active_keys()):
        try:
            out[k] = scoreboard(k, date=date)
        except Exception:
            out[k] = []
    return out


def summary(keys=None):
    """Lightweight counts for nav badges: {league: {'live': n, 'total': n}}."""
    res = {}
    for k, games in scoreboard_many(keys).items():
        res[k] = {
            "live": sum(1 for g in games if g["state"] == "in"),
            "total": len(games),
        }
    return res
