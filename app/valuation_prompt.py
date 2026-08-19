"""
Rigorlytics - turn a question into a valuation prompt block.

Bridges app.valuation (which computes) and app.rag (which narrates). Pulls a
player name out of the question, runs the analysis, and renders it as text the
model may quote from and nothing else.

The rendered block states, explicitly, what the model is allowed to claim. For
leagues with no licensed salary data the money section is replaced by a
prohibition, so a WNBA or college question cannot produce a salary sentence
even if the model would like to invent one.
"""

import re

try:
    from app.valuation import analyze
except ImportError:
    from valuation import analyze


# Words that start a sentence or a question and are capitalised for grammar,
# not because they are part of a name.
STOP = {
    "what", "who", "how", "why", "when", "where", "which", "is", "are", "was",
    "were", "does", "do", "did", "should", "would", "could", "can", "will",
    "the", "a", "an", "and", "but", "or", "if", "in", "on", "for", "to", "of",
    "at", "by", "with", "about", "worth", "value", "compare", "compared",
    "vs", "versus", "tell", "me", "give", "show", "his", "her", "their",
    "much", "many", "good", "better", "best", "he", "she", "they", "it",
}

# Team and league words that look like names but are not players.
NOT_PLAYERS = {
    "premier league", "major league", "major league soccer", "national football",
    "united states", "new york", "los angeles", "manchester united",
    "manchester city", "real madrid", "atlanta united", "inter miami",
}

TOKEN = re.compile(r"[A-Z][A-Za-zÀ-ɏ'’\-]+")

# Lowercase name particles that sit inside a surname and must not break a run:
# "Virgil van Dijk", "Alexis Mac Allister", "Kevin De Bruyne".
PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "da", "das",
             "dos", "di", "du", "la", "le", "el", "al", "bin", "ibn", "mac",
             "mc", "st", "ter", "ten"}


def extract_names(question, max_len=3):
    """Runs of consecutive capitalised words, longest first.

    'What is Bukayo Saka worth?' -> ['Bukayo Saka']
    Scans the raw text so word order and adjacency are preserved.
    """
    if not question:
        return []
    runs, current = [], []
    for word in re.split(r"(\s+)", question):
        w = word.strip()
        if not w:
            continue
        core = w.strip(".,!?;:()[]\"'")
        if TOKEN.fullmatch(core) and core.lower() not in STOP:
            current.append(core)
        elif current and core.lower() in PARTICLES:
            current.append(core)
        else:
            while current and current[-1].lower() in PARTICLES:
                current.pop()
            if len(current) >= 2:
                runs.append(current)
            current = []
    while current and current[-1].lower() in PARTICLES:
        current.pop()
    if len(current) >= 2:
        runs.append(current)

    out = []
    for run in runs:
        for size in range(min(max_len, len(run)), 1, -1):
            for i in range(len(run) - size + 1):
                cand = " ".join(run[i:i + size])
                if cand.lower() not in NOT_PLAYERS and cand not in out:
                    out.append(cand)
    out.sort(key=lambda s: -len(s.split()))
    return out[:6]


def money_str(amount, currency):
    if amount is None:
        return "unknown"
    return "%s %s" % (currency, format(int(amount), ","))


def both_str(m):
    """Euro figures carry their dollar equivalent, converted at the rate on the
    figure's own date. Dollar-native figures print once."""
    if not m:
        return "no money data"
    base = money_str(m.get("amount"), m.get("currency"))
    usd = m.get("amount_usd")
    if usd and m.get("currency") != "USD":
        base += " (%s)" % money_str(usd, "USD")
    return base


def pair_str(eur, usd, currency="EUR"):
    out = money_str(eur, currency)
    if usd is not None and currency != "USD":
        out += " (%s)" % money_str(usd, "USD")
    return out


def render_for_prompt(obj):
    """Analysis object -> the text block handed to the model."""
    if not obj or not obj.get("ok"):
        return ""
    p, c, m = obj["player"], obj["cohort"], obj["money"]
    conf = obj["confidence"]
    L = []

    L.append("PLAYER VALUATION (computed by Rigorlytics. Narrate these numbers; "
             "do not recompute, round differently, or add figures of your own):")
    L.append("Player: %s | %s | %s | age %s%s"
             % (p["name"], p["league"], p["position"], p["age"],
                (" | " + p["team"]) if p.get("team") else ""))
    L.append("Season %s, %s %s played"
             % (obj["season"]["year"], int(obj["season"]["workload"]),
                "minutes" if p["sport"] != "football" else "games"))
    L.append("Cohort: %d %s in %s (%s)"
             % (c["n"], c["position_group"], c["league"], c["definition"]))
    if obj.get("composite_percentile") is not None:
        L.append("Composite percentile across all measured metrics: %s"
                 % obj["composite_percentile"])
    L.append("Confidence: %s - %s" % (conf["tier"], "; ".join(conf["reasons"])))

    L.append("")
    L.append("METRICS (value | percentile within cohort | cohort median):")
    for x in obj["metrics"]:
        note = "" if x["higher_is_better"] else "  [lower is better]"
        if x.get("no_variance"):
            note += "  [every peer records the same value - not a differentiator]"
        L.append("  %s (%s): %s | %s | %s%s"
                 % (x["label"], x["mode"], x["value"],
                    "n/a" if x["percentile"] is None else "%.0f" % x["percentile"],
                    x["cohort_median"], note))

    if obj.get("comparables"):
        band = m.get("band") or {}
        ab = band.get("age_band")
        L.append("")
        L.append("CLOSEST STATISTICAL COMPARABLES%s:"
                 % (" (within %.1f years of age)" % ab if ab else ""))
        for cmp_ in obj["comparables"]:
            mo = cmp_.get("money")
            pp = cmp_.get("postseason")
            play = ("; %s playoffs: %s games" % (pp["year"], pp.get("games") or "?")
                    if pp else "; no postseason record")
            L.append("  %s%s%s - %s%s"
                     % (cmp_["player"],
                        (" (%s)" % cmp_["team"]) if cmp_.get("team") else "",
                        (", age %s" % cmp_["age"]) if cmp_.get("age") else "",
                        both_str(mo), play))

    ps = obj.get("postseason") or {}
    L.append("")
    if not ps.get("has_data"):
        L.append("POSTSEASON: %s" % ps.get("note", "no playoff data held."))
    else:
        L.append("POSTSEASON (%s playoffs, %s games):"
                 % (ps.get("year"), ps.get("games") or "?"))
        if ps.get("split"):
            L.append("  Playoff rate vs this player's OWN regular-season rate:")
            for r in ps["split"]:
                arrow = ("" if r.get("change_pct") is None
                         else "  (%+.1f%%)" % r["change_pct"])
                L.append("    %s: %s regular -> %s playoffs%s"
                         % (r["label"], r["regular"], r["postseason"], arrow))
            L.append("  A rise or fall here is about this player only. It is a "
                     "small sample by nature - say so rather than declaring him "
                     "clutch or a choker.")
        else:
            L.append("  Playoff row held, but no rate metric overlaps the regular "
                     "season, so no comparison is possible.")

    L.append("")
    if not m.get("axis"):
        L.append("MONEY: none. %s does not publish salary data and Rigorlytics "
                 "holds none for this league." % p["league"])
        L.append("YOU MUST NOT state, estimate, or imply any salary, contract "
                 "value, or market value for this player. Answer on performance "
                 "and comparables only.")
    else:
        mine = m.get("player")
        L.append("MONEY AXIS: %s (%s)" % (m["axis"], m["axis_label"]))
        if mine:
            extra = []
            if mine.get("contract_expires"):
                extra.append("contract expires %s" % mine["contract_expires"])
            if mine.get("agent"):
                extra.append("agent %s" % mine["agent"])
            L.append("Actual: %s%s"
                     % (both_str(mine),
                        ("  (" + ", ".join(extra) + ")") if extra else ""))
        else:
            L.append("Actual: not held for this player - do not guess it.")
        b = m.get("band")
        if b:
            L.append("Projected band from comparables: %s to %s (midpoint %s)"
                     % (pair_str(b["low"], b.get("low_usd"), b["currency"]),
                        pair_str(b["high"], b.get("high_usd"), b["currency"]),
                        pair_str(b["mid"], b.get("mid_usd"), b["currency"])))
            L.append("Band basis: %s" % b["basis"])
            if b.get("verdict"):
                L.append("VERDICT: the actual figure sits %s the projected band "
                         "(%s versus the midpoint)."
                         % (b["verdict"].upper(),
                            money_str(abs(b["gap_vs_mid"]), b["currency"])))
                L.append("The band is a projection from comparable players, not "
                         "an appraisal. Say so if you cite it.")
        else:
            L.append("No projected band: too few comparables carry money data.")

    if m.get("axis") == "market_value":
        L.append("Dollar figures are the euro amount converted at the European "
                 "Central Bank reference rate on that figure's own date, not at "
                 "today's rate. Quote either currency; do not convert yourself.")

    L.append("")
    L.append("CLAIM RULES: percentiles, rates and the comparable set are computed "
             "by Rigorlytics and may be stated as fact. The projected band is an "
             "inference and must be described as such. Any number not printed "
             "above must not appear in your answer.")
    if conf["tier"] != "high":
        L.append("Confidence is %s - open your answer with that caveat before "
                 "any conclusion." % conf["tier"])
    return "\n".join(L)


def valuation_context(question, max_players=1, max_tries=3):
    """Question -> rendered block, or '' when no player resolves.

    Capped at max_tries candidates: each one costs a database round trip, and
    this runs inside a chat request.
    """
    blocks = []
    for name in extract_names(question)[:max_tries]:
        try:
            obj = analyze(name)
        except Exception:
            continue
        if obj.get("ok"):
            blocks.append(render_for_prompt(obj))
            if len(blocks) >= max_players:
                break
    return "\n\n".join(blocks)
