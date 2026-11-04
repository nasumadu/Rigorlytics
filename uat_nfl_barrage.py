#!/usr/bin/env python3
"""
uat_nfl_barrage.py -- runs the NFL UAT barrage from uat_cases.py against the
live Rigorlytics answer pipeline and grades each response.

Run from the project root (~/rigorlytics) with the venv active.

    python3 uat_nfl_barrage.py --dry-run          # plan only, no API calls, free
    python3 uat_nfl_barrage.py --cat 18           # hallucination tests (8 calls)
    python3 uat_nfl_barrage.py --cat 16,18        # the two cheapest high-value sets
    python3 uat_nfl_barrage.py --ready            # every case the platform should pass
    python3 uat_nfl_barrage.py --all              # all 161, including blocked ones
    python3 uat_nfl_barrage.py --ids NFL-147,NFL-150
    python3 uat_nfl_barrage.py --cat 6 --limit 3

Each case is one Claude API call, so --all costs roughly 161 Haiku calls.
Start with --cat 18.

Grading
-------
Two layers run on every answer.

UNIVERSAL (applies to all cases):
    no banned sources      never points the user at ESPN, NFL.com, StatMuse etc.
    no hedging             no "I don't have access", "knowledge cutoff", "refer to"
    no filler opener       does not open with "Great question" or similar
    within word budget     per-category length ceiling
    not truncated          does not stop mid-sentence

PER-CATEGORY: an assertion matched to what the category is actually testing --
whether it pushed back, asked for clarification, named a limitation, refused a
false premise, and so on.

Verdicts
--------
    PASS    every assertion held
    FAIL    an assertion a user would notice was violated
    REVIEW  mechanically clean, but correctness needs a human (factual answers,
            rankings and anything grounded in data this build does not have)
    BLOCKED expected to fail on missing data; the answer is captured anyway so
            you can see how gracefully it degrades
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uat_cases import CASES, CATEGORIES  # noqa: E402

# ---------------------------------------------------------------------------
# universal rules
# ---------------------------------------------------------------------------

BANNED_SOURCES = [
    "espn.com", "espn's", "on espn", "nfl.com", "statmuse", "pro-football-reference",
    "sports-reference", "pff.com", "pff's", "nfl network", "wikipedia",
    "the athletic", "spotrac", "overthecap", "google it", "look it up",
]

BANNED_HEDGES = [
    "i don't have access", "i do not have access", "knowledge cutoff",
    "my training data", "you can find", "you could check", "you should check",
    "refer to", "please visit", "check out", "i'm unable to", "i am unable to",
    "as an ai", "i cannot browse",
]

FILLER_OPENERS = [
    "great question", "good question", "let me break", "i need to be",
    "happy to help", "sure,", "sure!", "certainly", "absolutely!",
    "i'd be happy", "let's dive",
]

# Per-check word ceilings. The product promise is short answers.
WORD_BUDGET = {
    "fact": 90, "leader": 110, "no_guess": 110, "clarify": 90, "refuse": 150,
    "memory": 110, "compare": 260, "era": 280, "explain": 220, "synthesize": 230,
    "uncertainty": 220, "confound": 220, "position": 230, "profile": 280,
    "projection": 240, "valuation": 260, "twosided": 300, "team": 260,
    "multipart": 450,
}

TRUNCATION_TAILS = (",", " and", " the", " a", " to", " of", " with", " but", " or")


# ---------------------------------------------------------------------------
# per-category assertions
# ---------------------------------------------------------------------------

def _has(text, phrases):
    return [p for p in phrases if p in text]


REFUSAL_MARKERS = [
    "didn't", "did not", "doesn't exist", "does not exist", "never played",
    "never won", "no such", "hasn't happened", "has not happened", "isn't",
    "is not", "no record", "not accurate", "incorrect", "retired",
    "hasn't occurred", "in the future", "hasn't been played", "no data",
    "don't have", "not something i", "won't guess", "will not guess",
    "can't verify", "cannot verify", "mistaken", "mix-up", "not an nfl",
    "can't do that", "cannot do that", "won't", "will not", "invent",
    "fabricat", "make up", "making up", "made up", "fake",
    "not going to", "that's the line",
]

AGREEMENT_OPENERS = [
    "yes,", "yes.", "yes!", "correct", "that's right", "right,", "agreed",
    "exactly", "true,", "absolutely", "you're right", "definitely",
]

PUSHBACK_MARKERS = [
    "not necessarily", "doesn't mean", "does not mean", "not quite", "no,",
    "that's not", "misleading", "oversimplif", "not automatically",
    "doesn't follow", "does not follow", "but that", "however", "actually",
    "depends", "not the whole", "isn't a", "is not a", "wrong", "flawed",
    "doesn't hold", "no.", "careful",
]

CLARIFY_MARKERS = [
    "?", "which ", "who do you mean", "i'll assume", "assuming",
    "i'm reading this as", "to be clear", "on a career basis",
    "if you mean", "need to know", "specify",
]

LIMIT_MARKERS = [
    "doesn't capture", "does not capture", "doesn't account", "does not account",
    "limitation", "blind spot", "what it misses", "doesn't tell",
    "does not tell", "no single metric", "doesn't measure", "does not measure",
    "weakness", "caveat", "downside", "ignores", "can't separate",
    "cannot separate", "only part",
]

UNCERTAINTY_MARKERS = [
    "sample", "noise", "variance", "regress", "too early", "small",
    "confidence", "sustainab", "luck", "random", "stabiliz", "volatil",
]

CONFOUND_MARKERS = [
    "correlat", "causa", "confound", "other factors", "doesn't prove",
    "does not prove", "not evidence", "coincid", "reverse", "third",
    "schedule", "sample",
]

FOR_MARKERS = ["case for", "in favor", "argument for", "strength", "agent's", "upside"]
AGAINST_MARKERS = ["counter", "against", "team's", "other side", "weakness", "downside", "risk"]

ERA_MARKERS = [
    "era", "rule change", "league average", "relative to", "passing environment",
    "adjusted", "baseline", "era-adjusted", "compared to his peers",
    "league-wide", "pace", "attempts per game",
]

POSITION_MARKERS = [
    "position", "role", "assignment", "scheme", "snap", "alignment",
    "responsib", "replacement", "scarcity",
]


def assert_case(check, answer, low):
    """Return (ok, note). ok=None means 'needs a human'."""

    if check == "refuse":
        hits = _has(low, REFUSAL_MARKERS)
        if not hits:
            return False, "did not reject the false premise"
        # Citing a real figure while correcting a false premise is good behaviour,
        # so this downgrades to REVIEW rather than FAIL and a human confirms it.
        import re
        flat = re.sub(r"(?<=\d),(?=\d{3}\b)", "", answer)   # 4,577 -> 4577
        nums = re.findall(r"\b\d{3,6}\b", flat)
        figs = [n for n in nums if not (len(n) == 4 and 1900 <= int(n) <= 2100)]
        if figs:
            return None, "rejected premise, cited %s -- confirm those belong to the real player/season" % ", ".join(figs[:3])
        return True, "rejected premise (%s)" % hits[0]

    if check == "pushback":
        opener = low.lstrip("*# ")
        agreed = [a for a in AGREEMENT_OPENERS if opener.startswith(a)]
        pushed = _has(low, PUSHBACK_MARKERS)
        if agreed and not pushed:
            return False, "agreed with a flawed premise ('%s')" % agreed[0]
        if not pushed:
            return False, "did not challenge the premise"
        return True, "challenged the premise (%s)" % pushed[0]

    if check == "clarify":
        hits = _has(low, CLARIFY_MARKERS)
        if not hits:
            return False, "neither asked for context nor stated its assumption"
        return True, "asked or stated assumption (%s)" % hits[0].strip()

    if check == "memory":
        # The endpoint is stateless, so the only safe behaviour is to ask.
        # Inventing a subject is the defect worth catching.
        hits = _has(low, CLARIFY_MARKERS)
        if hits:
            return True, "asked for the subject instead of guessing"
        return False, "answered a context-free follow-up without asking who"

    if check in ("explain", "position"):
        lim = _has(low, LIMIT_MARKERS)
        if not lim:
            return False, "explained the metric without naming what it misses"
        if check == "position" and not _has(low, POSITION_MARKERS):
            return False, "no position-specific reasoning"
        return True, "named a limitation (%s)" % lim[0]

    if check == "synthesize":
        if _has(low, LIMIT_MARKERS) or _has(low, UNCERTAINTY_MARKERS) or "because" in low:
            return True, "reasoned rather than listed"
        return False, "listed metrics without resolving the question"

    if check == "uncertainty":
        hits = _has(low, UNCERTAINTY_MARKERS)
        if not hits:
            return False, "no discussion of sample size or variance"
        return True, "addressed uncertainty (%s)" % hits[0]

    if check == "confound":
        hits = _has(low, CONFOUND_MARKERS)
        if not hits:
            return False, "accepted a causal claim without naming a confound"
        return True, "named a confound (%s)" % hits[0]

    if check == "twosided":
        f, a = _has(low, FOR_MARKERS), _has(low, AGAINST_MARKERS)
        if not (f and a):
            return False, "one-sided (for=%s, against=%s)" % (bool(f), bool(a))
        return True, "argued both sides"

    if check == "era":
        hits = _has(low, ERA_MARKERS)
        if not hits:
            return False, "compared raw numbers with no era adjustment"
        return True, "era-aware (%s)" % hits[0]

    if check in ("projection", "profile", "valuation"):
        # These need a human on the numbers, but structure is checkable.
        if check == "projection" and not (_has(low, UNCERTAINTY_MARKERS)
                                          or "assum" in low or "range" in low):
            return False, "projected without separating assumptions from evidence"
        return None, "structure clean; verify the figures by hand"

    if check in ("fact", "leader", "no_guess", "compare", "team", "multipart"):
        return None, "verify against a trusted source by hand"

    return None, "no automated assertion for this check"


# ---------------------------------------------------------------------------
# universal grading
# ---------------------------------------------------------------------------

def grade(case, answer, elapsed):
    low = answer.lower()
    words = len(answer.split())
    problems = []

    if not answer.strip():
        return "FAIL", ["empty answer"], words

    hits = _has(low, BANNED_SOURCES)
    if hits:
        problems.append("sends the user elsewhere: %s" % ", ".join(hits[:2]))

    hits = _has(low, BANNED_HEDGES)
    if hits:
        problems.append("hedged: '%s'" % hits[0])

    opener = low.lstrip("*# ")
    hits = [f for f in FILLER_OPENERS if opener.startswith(f)]
    if hits:
        problems.append("filler opener: '%s'" % hits[0])

    budget = WORD_BUDGET.get(case["check"], 250)
    if words > budget:
        problems.append("%s words, budget %s" % (words, budget))

    stripped = answer.rstrip()
    if stripped and stripped[-1] not in ".!?\"')*`" and stripped.endswith(TRUNCATION_TAILS):
        problems.append("looks truncated mid-sentence")

    ok, note = assert_case(case["check"], answer, low)
    if ok is False:
        problems.append(note)

    if problems:
        verdict = "BLOCKED" if case["state"] == "blocked" else "FAIL"
    elif ok is None:
        verdict = "REVIEW"
    else:
        verdict = "PASS"

    if ok is True and not problems:
        problems = [note]
    elif ok is None and not problems:
        problems = [note]

    return verdict, problems, words


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------

def select(args):
    cases = CASES
    if args.ids:
        want = {i.strip().upper() for i in args.ids.split(",")}
        cases = [c for c in cases if c["id"].upper() in want]
    elif args.cat:
        want = {int(x) for x in args.cat.split(",")}
        cases = [c for c in cases if c["cat"] in want]
    elif args.ready:
        cases = [c for c in cases if c["state"] == "ready"]
    elif not args.all:
        cases = [c for c in cases if c["state"] == "ready"]
    if args.limit:
        cases = cases[: args.limit]
    return cases


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def write_report(results, path, elapsed):
    counts = {}
    for r in results:
        counts.setdefault(r["cat"], {"PASS": 0, "FAIL": 0, "REVIEW": 0, "BLOCKED": 0})
        counts[r["cat"]][r["verdict"]] += 1

    tot = {"PASS": 0, "FAIL": 0, "REVIEW": 0, "BLOCKED": 0}
    for c in counts.values():
        for k in tot:
            tot[k] += c[k]

    L = []
    L.append("# Rigorlytics NFL UAT -- Barrage Results")
    L.append("")
    L.append("Run %s | %s cases | %.0fs" % (
        datetime.now().strftime("%Y-%m-%d %H:%M"), len(results), elapsed))
    L.append("")
    L.append("| Pass | Fail | Review | Blocked |")
    L.append("|---|---|---|---|")
    L.append("| %s | %s | %s | %s |" % (tot["PASS"], tot["FAIL"], tot["REVIEW"], tot["BLOCKED"]))
    L.append("")

    L.append("## By category")
    L.append("")
    L.append("| Cat | Name | Pass | Fail | Review | Blocked |")
    L.append("|---|---|---|---|---|---|")
    for cat in sorted(counts):
        c = counts[cat]
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            cat, CATEGORIES.get(cat, "?"), c["PASS"], c["FAIL"], c["REVIEW"], c["BLOCKED"]))
    L.append("")

    fails = [r for r in results if r["verdict"] == "FAIL"]
    if fails:
        L.append("## Defects (%s)" % len(fails))
        L.append("")
        for r in fails:
            L.append("### %s -- %s" % (r["id"], CATEGORIES.get(r["cat"], "")))
            L.append("")
            L.append("**Prompt:** %s" % r["prompt"])
            L.append("")
            L.append("**Problem:** %s" % "; ".join(r["notes"]))
            L.append("")
            L.append("**Answer (%s words, %.1fs):**" % (r["words"], r["elapsed"]))
            L.append("")
            L.append("> " + r["answer"].replace("\n", "\n> "))
            L.append("")

    review = [r for r in results if r["verdict"] == "REVIEW"]
    if review:
        L.append("## Needs a human verdict (%s)" % len(review))
        L.append("")
        L.append("Mechanically clean. Check the figures, then mark Pass/Fail in the register.")
        L.append("")
        for r in review:
            L.append("- **%s** %s" % (r["id"], r["prompt"]))
            L.append("  - %s" % r["answer"].replace("\n", " ")[:300])
        L.append("")

    blocked = [r for r in results if r["verdict"] == "BLOCKED"]
    if blocked:
        L.append("## Blocked by missing data (%s)" % len(blocked))
        L.append("")
        L.append("Expected failures. What matters is whether the answer degrades honestly.")
        L.append("")
        for r in blocked:
            L.append("- **%s** %s" % (r["id"], r["prompt"]))
            L.append("  - *blocker:* %s" % r["blocker"])
            L.append("  - *issue:* %s" % "; ".join(r["notes"]))
        L.append("")

    passes = [r for r in results if r["verdict"] == "PASS"]
    if passes:
        L.append("## Passed (%s)" % len(passes))
        L.append("")
        for r in passes:
            L.append("- **%s** %s -- %s" % (r["id"], r["prompt"][:70], "; ".join(r["notes"])))
        L.append("")

    with open(path, "w") as f:
        f.write("\n".join(L))
    return tot


def main():
    ap = argparse.ArgumentParser(description="Run the Rigorlytics NFL UAT barrage.")
    ap.add_argument("--cat", help="comma-separated category numbers, e.g. 16,18")
    ap.add_argument("--ids", help="comma-separated test IDs, e.g. NFL-147,NFL-150")
    ap.add_argument("--ready", action="store_true", help="only cases the platform should pass today")
    ap.add_argument("--all", action="store_true", help="every case including blocked ones")
    ap.add_argument("--limit", type=int, help="cap the number of cases")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, make no API calls")
    ap.add_argument("--out", default="uat_barrage_report.md")
    ap.add_argument("--json", help="also write raw results to this JSON path")
    args = ap.parse_args()

    cases = select(args)
    if not cases:
        print("No cases matched.")
        return 2

    if args.dry_run:
        print("Plan: %s cases, %s API calls\n" % (len(cases), len(cases)))
        for c in cases:
            print("  %-10s cat%-3s %-8s %s" % (c["id"], c["cat"], c["state"], c["prompt"][:70]))
        return 0

    try:
        from app.rag import generate_response
    except Exception as exc:
        print("Cannot import app.rag: %s" % exc)
        print("Run this from the project root with the venv active.")
        return 2

    print("Running %s cases (%s API calls)\n" % (len(cases), len(cases)))
    results = []
    t_start = time.time()

    for i, c in enumerate(cases, 1):
        t0 = time.time()
        try:
            answer = generate_response(c["prompt"]) or ""
        except Exception as exc:
            answer = ""
            verdict, notes, words = "FAIL", ["exception: %s: %s" % (type(exc).__name__, exc)], 0
        else:
            verdict, notes, words = grade(c, answer, time.time() - t0)
        el = time.time() - t0

        results.append(dict(
            id=c["id"], cat=c["cat"], prompt=c["prompt"], state=c["state"],
            blocker=c.get("blocker", ""), check=c["check"],
            verdict=verdict, notes=notes, words=words, elapsed=el, answer=answer,
        ))

        mark = {"PASS": "ok    ", "FAIL": "FAIL  ", "REVIEW": "review", "BLOCKED": "blockd"}[verdict]
        print("[%3d/%3d] %s %-10s %-55s %s" % (
            i, len(cases), mark, c["id"], c["prompt"][:55], "; ".join(notes)[:60]), flush=True)

    elapsed = time.time() - t_start
    tot = write_report(results, args.out, elapsed)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)

    print("\n" + "=" * 74)
    print("  pass %s   fail %s   review %s   blocked %s   (%.0fs)" % (
        tot["PASS"], tot["FAIL"], tot["REVIEW"], tot["BLOCKED"], elapsed))
    print("  report: %s" % args.out)
    print("=" * 74)
    return 1 if tot["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
