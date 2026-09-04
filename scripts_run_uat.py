#!/usr/bin/env python3
"""
Rigorlytics - NFL UAT runner.

Sends each test prompt to the answering pipeline, applies mechanical checks that
code can decide objectively, then optionally asks a separate judge model to score
the dimensions that need judgement.

The split matters. A judge model does not know what is in this database, so it
cannot reliably tell a real figure from an invented one. Code can: if a case is
tagged db_absent or impossible and the answer states a precise statistic, that is
a fabrication regardless of how well written the answer is.

    python scripts_run_uat.py --phase1                       # 38 highest-value cases
    python scripts_run_uat.py --all --target local
    python scripts_run_uat.py --ids NFL-147,NFL-148 --judge
    python scripts_run_uat.py --phase1 --target live --live-url https://rigorlytics.net/api/ask
    python scripts_run_uat.py --category 18 --judge

Writes uat/results-<target>.json, .csv and .html
"""

import os, sys, re, csv, json, time, argparse, datetime

sys.path.insert(0, os.getcwd())
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from uat_nfl_cases import CASES, PHASE_1, CATEGORIES, by_ids

OUT_DIR = "uat"

# A specific football statistic being asserted. Deliberately narrow: we want
# fabricated *figures*, not any use of a number.
NUM = r"\d{1,3}(?:,\d{3})+|\d+"
STAT_PATTERNS = [
    r"\b(?:%s)\s*(?:passing|rushing|receiving|total)?\s*yards\b" % NUM,
    r"\b\d{1,3}\s*(?:passing|rushing|receiving)?\s*touchdowns?\b",
    r"\b\d{1,3}\s*TDs?\b",
    r"\b\d{1,3}\s*INTs?\b",
    r"\b\d{1,3}(?:\.\d{1,2})?\s*:\s*1\b",
    r"\b\d{1,3}(?:\.\d{1,2})?\s*(?:completion|comp)\s*(?:%|pct|percentage)",
    r"\b\d{1,3}(?:st|nd|rd|th)\s*percentile\b",
    r"\b\d{1,3}(?:\.\d)?\s*sacks?\b",
    r"\b\d{1,3}\s*interceptions?\b",
    r"\bpasser rating of \d{1,3}(?:\.\d)?",
    r"\b\d{1,3}\.\d\s*(?:passer rating|QBR|rating)\b",
    r"\b\d{1,2}-\d{1,2}\s*(?:record|in the playoffs)\b",
    r"\$\s?\d[\d,.]*\s*(?:million|m\b|billion)",
    r"\bthrew for \d[\d,]*",
    r"\b\d{1,2}\s*Super Bowls?\b",
]
REFUSAL = [
    "don't have", "do not have", "no data", "not in", "cannot find", "can't find",
    "unable to", "don't hold", "do not hold", "isn't in", "is not in",
    "no record", "never played", "didn't happen", "did not happen",
    "doesn't exist", "does not exist", "incorrect premise", "false premise",
    "not accurate", "hasn't happened", "has not happened", "outside", "beyond",
    "no such", "won't guess", "will not guess", "can't verify", "cannot verify",
    "there is no", "there was no", "there's no", "can't provide", "cannot provide",
    "won't provide", "never played for", "never won", "didn't play", "did not play",
    "no valid", "not a real", "isn't a real", "hasn't been played", "in the future",
    "yet to", "premise", "retired", "different sport", "never a", "wasn't an nfl",
    "not valid", "isn't valid", "is not valid", "invalid", "not comparable",
    "not an nfl", "never an nfl", "basketball", "baseball", "not a football",
    "doesn't apply", "does not apply", "mistaken", "confusion", "mix-up",
    "isn't possible", "is not possible", "not possible", "wasn't in the league",
    "was not in the league", "years old", "hadn't been", "had not been",
    "didn't enter", "did not enter", "not yet", "impossible",
    # Refusing outright is a pass. Rigorlytics phrases this in its own voice,
    # so match the refusal itself, not just "no data".
    "won't do that", "will not do that", "not doing that", "i'm not doing",
    "won't fabricate", "will not fabricate", "won't invent", "will not invent",
    "won't make up", "will not make up", "refuse", "i won't", "i will not",
    "not going to guess", "never signed", "never with", "not fabricate",
    "won't pretend", "don't want to fabricate", "wouldn't be real",
    # Observed refusals the list missed. NFL-148 rejected an impossible premise
    # in exactly the right words and was scored a hard failure for it.
    "cannot make that", "can't make that", "cannot compare", "can't compare",
    "cannot answer", "can't answer", "i cannot", "i can't", "neither player",
    "doesn't have", "does not have", "has no ", "have no ", "no season",
    "outside that scope", "falls outside", "not something i can",
]
CHALLENGE = [
    "not necessarily", "doesn't follow", "does not follow", "that's not",
    "that is not", "misleading", "oversimplif", "however", "but that",
    "isn't the whole", "more complicated", "depends", "correlat", "confound",
    "not a reliable", "on its own", "by itself", "caution",
]
CLARIFY = [
    "which ", "who do you mean", "could you", "can you clarify", "do you mean",
    "i'll assume", "i will assume", "assuming", "to answer this i", "if you mean",
    "depends on what", "several ways", "define", "framework", "specify",
    "once you tell me", "tell me what", "what you're valuing", "not going to name",
    "gets evaluated on", "dimensions", "need you to", "narrow it", "which era",
    "depends", "criteria",
    # Naming the basis of an answer is stating assumptions, and asking for the
    # missing subject is the correct handling of a pronoun with no antecedent.
    "i need a name", "need a name", "need a player", "tell me the player",
    "i need a", "give me a name", "in this database", "in this data",
    "across the", "by that measure", "on that basis", "which season",
    "what i can actually access", "not in 2025",
    # Declining is a valid response to an under-specified question - NFL-112
    # said "I can't answer this" and named the missing data, then failed the
    # clarification check for it.
    "can't answer", "cannot answer", "outside that scope", "falls outside",
    "i need to know", "which player", "no salary", "zero salary",
]
UNCERTAIN = [
    "uncertain", "sample", "small sample", "regress", "variance", "noise",
    "too early", "not enough", "caution", "confidence", "likely", "may ",
    "might ", "could ", "tentative", "unstable", "volatil",
]
CAUSAL_HEDGE = [
    "correlat", "causa", "confound", "doesn't prove", "does not prove",
    "not proof", "other factors", "alone", "on its own", "context",
]


def has_any(text, needles):
    t = (text or "").lower()
    return [n for n in needles if n in t]


_FIG_CACHE = {}


def db_figures(entities):
    """Every numeric value we actually hold for the named players.

    A tag saying "this is not in the database" is only as good as my assumption
    when I wrote it. Asking the database directly is the honest check: a figure
    that appears in a stored row is corroborated, one that does not is the
    model supplying it from memory.
    """
    if not entities:
        return None
    key = tuple(sorted(entities))
    if key in _FIG_CACHE:
        return _FIG_CACHE[key]
    vals = set()
    try:
        from app.db import get_conn
        with get_conn() as c:
            cur = c.cursor()
            for e in entities:
                per_key = {}          # per player: Brady's total is not Brady+Manning
                cur.execute("""SELECT ps.stats AS st, s.year AS yr, p.id AS pid
                               FROM players p
                               JOIN player_seasons ps ON ps.player_id = p.id
                               JOIN seasons s ON s.id = ps.season_id
                               WHERE p.full_name ILIKE %s LIMIT 400""",
                            ("%" + e + "%",))
                for row in cur.fetchall():
                    row = dict(row)
                    st = row["st"]
                    if isinstance(st, str):
                        try:
                            st = json.loads(st)
                        except ValueError:
                            continue
                    for k, v in (st or {}).items():
                        if isinstance(v, (int, float)):
                            vals.add(float(v))
                            # Keyed by player, not by search term: "Brady"
                            # also matches Brady Quinn, and summing them
                            # together produces a career total belonging to
                            # nobody.
                            per_key.setdefault((row["pid"], k), []).append(float(v))
                    if row["yr"]:
                        vals.add(float(row["yr"]))
                # Totals and means are legitimate figures: Rigorlytics computes
                # them in history() and hands them over. They appear in no single
                # row, so corroboration must include them - and they must be
                # computed INSIDE this loop, per player. Left outside it, the
                # per_key reset meant only the last entity's aggregates survived,
                # so Brady's career total looked invented.
                for k, series in per_key.items():
                    if series:
                        vals.add(float(sum(series)))
                        vals.add(round(sum(series) / len(series), 3))
                        vals.add(float(max(series)))
                        vals.add(float(min(series)))
    except Exception:
        return None
    _FIG_CACHE[key] = vals
    return vals


NUMTOK = re.compile(r"\d[\d,]*(?:\.\d+)?")


def leaderboard_figures(question, depth=60):
    """Every value on the ranking a leader question asks about.

    A question like "who led the NFL in passing yards in 2020" names no player,
    so entity-based corroboration has nothing to check against. The ranking
    itself is the ground truth.
    """
    try:
        from app.leaders import detect, leaders
    except Exception:
        return None
    spec = detect(question)
    if not spec:
        return None
    try:
        rows, meta = leaders(spec["stat"], spec["league"], spec["year"],
                             spec["season_type"], depth)
    except Exception:
        return None
    if not rows:
        return None
    vals = {float(r["v"]) for r in rows if r.get("v") is not None}
    if meta and meta.get("year"):
        vals.add(float(meta["year"]))
    return vals


_ENT_CACHE = {}


def resolve_entity(name, text=None):
    """A bare surname to the player the question is actually about.

    find_players matches on a prefix, so "Brady" reaches Brady Poppinga and
    "Manning" reaches nobody. Test entities are surnames almost without
    exception, so match anywhere in the name, prefer a candidate whose LAST
    token is the surname, and break ties on seasons held - which is what
    separates Tom Brady from Brady Quinn.
    """
    rows = _ENT_CACHE.get(name)
    if rows is None:
        rows = _entity_rows(name)
        _ENT_CACHE[name] = rows
    if not rows:
        return None
    low = name.strip().lower()
    surname = [r for r in rows
               if (r["nm"] or "").strip().lower().split()[-1:] == [low]]
    pick = surname or rows
    # Seasons held is the wrong tie-break when the answer names the player:
    # Tony Jefferson has more seasons than Justin, but only one of them is
    # being discussed. Prefer whoever the text actually mentions.
    if text:
        t = text.lower()
        named = [r for r in pick if (r["nm"] or "").lower() in t]
        if named:
            return named[0]["nm"]
    return pick[0]["nm"]


def _entity_rows(name):
    try:
        from app.db import get_conn
        with get_conn() as c:
            cur = c.cursor()
            cur.execute("""
                SELECT p.full_name AS nm, count(ps.id) AS n
                FROM players p
                LEFT JOIN player_seasons ps ON ps.player_id = p.id
                WHERE p.full_name ILIKE %s
                GROUP BY p.full_name
                ORDER BY n DESC
                LIMIT 25
            """, ("%" + name + "%",))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


_COMP_CACHE = {}


def computed_figures(entities, text=None):
    """Everything Rigorlytics itself derives and hands to the model.

    db_figures reads stored rows. It cannot see the aggregates history()
    computes or the percentiles analyze() ranks, and it sums regular and
    postseason rows together while history() aggregates the regular season
    alone - so a correctly quoted career total can never match and gets
    reported as fabrication. Flagging figures the system supplied is worse
    than not checking at all: it buries the real failures under noise.
    """
    if not entities:
        return set()
    key = (tuple(sorted(entities)), hash(text or ""))
    if key in _COMP_CACHE:
        return _COMP_CACHE[key]
    out = set()
    try:
        from app.valuation import history, analyze
    except Exception:
        _COMP_CACHE[key] = out
        return out
    for e in entities:
        # Entities are bare surnames. history("Brady") resolves to Brady Murray
        # and history("Manning") to Paul Manning - real players, wrong ones, so
        # no total ever matches and every career figure reads as invented.
        # find_players ranks by seasons held, which puts the player the question
        # is actually about first.
        try:
            e = resolve_entity(e, text) or e
        except Exception:
            pass
        try:
            h = history(e)
        except Exception:
            h = None
        if h and h.get("ok"):
            for a in (h.get("aggregates") or {}).values():
                for f in ("mean", "total", "best"):
                    if isinstance(a.get(f), (int, float)):
                        out.add(float(a[f]))
            for row in (h.get("season_rows") or []):
                for v in (row.get("values") or {}).values():
                    if isinstance(v, (int, float)):
                        out.add(float(v))
        try:
            o = analyze(e)
        except Exception:
            o = None
        if o and o.get("ok"):
            if isinstance(o.get("composite_percentile"), (int, float)):
                out.add(float(o["composite_percentile"]))
            for m in (o.get("metrics") or []):
                for f in ("value", "percentile", "cohort_median"):
                    if isinstance(m.get(f), (int, float)):
                        out.add(float(m[f]))
    _COMP_CACHE[key] = out
    return out


def uncorroborated(text, entities, extra=None):
    """Figures asserted in the answer that match nothing we hold or computed."""
    held = db_figures(entities)
    if held is not None:
        held = held | computed_figures(entities, text)
    if extra:
        held = (held or set()) | extra
    if held is None:
        return []
    missing = []
    for frag in find_stats(text):
        m = NUMTOK.search(frag)
        if not m:
            continue
        try:
            n = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if n < 10 or (1900 <= n <= 2100 and n == int(n)):
            continue          # small counts and years are not distinctive
        # Answers round: 117.181 is quoted as 117.2. Allow a whole unit, or
        # 0.5% on large figures, before calling something unsupported.
        tol = max(1.0, abs(n) * 0.005)
        if not any(abs(n - h) <= tol for h in held):
            missing.append(frag)
    return missing


def find_stats(text):
    out = []
    for pat in STAT_PATTERNS:
        out += [m.group(0) for m in re.finditer(pat, text or "", re.I)]
    return out


# ------------------------------------------------------------------ targets

def local_answer(prompt, history=None):
    from app.rag import generate_response
    return generate_response(prompt)


def live_answer(prompt, url, tries=6):
    # The server calls a model per question, so a 154-case sweep trips a rate
    # limit partway through. Without backoff the suite stops measuring the
    # system and starts measuring the limiter.
    import urllib.request, urllib.error
    body = json.dumps({"question": prompt, "query": prompt}).encode()
    delay, last, raw = 5.0, None, None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "Rigorlytics-UAT/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = delay
            ra = e.headers.get("Retry-After") if e.headers else None
            if ra:
                try:
                    wait = max(wait, float(ra))
                except ValueError:
                    pass
            print("      HTTP %s - waiting %.0fs (attempt %d/%d)"
                  % (e.code, wait, attempt + 1, tries))
            time.sleep(wait)
            delay = min(delay * 2, 120.0)
        except Exception as e:
            last = e
            if attempt == tries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 120.0)
    if raw is None:
        raise last if last else RuntimeError("no response")
    try:
        d = json.loads(raw)
    except ValueError:
        return raw
    for k in ("answer", "response", "text", "message", "result"):
        if isinstance(d.get(k), str):
            return d[k]
    return raw


# ------------------------------------------------------------------ checks

def mechanical(case, answer):
    """Objective checks. Returns (checks, flags, hard_fail)."""
    tags = case["tags"]
    checks, flags = {}, []
    a = answer or ""

    if "db_absent" in tags or "impossible" in tags or "no_contract_data" in tags:
        acknowledged = bool(has_any(a, REFUSAL))
        board = None
        if "impossible" not in tags:
            q = case["prompt"] if isinstance(case["prompt"], str) else case["prompt"][0]
            board = leaderboard_figures(q)
        if board:
            # A leader question: check the answer against the real ranking.
            miss = uncorroborated(a, case["entities"], extra=board)
            ok = acknowledged or len(miss) < 2
            checks["figures_corroborated"] = ok
            if miss:
                flags.append("%d figure(s) not on the ranking: %s"
                             % (len(miss), "; ".join(miss[:4])))
        elif "impossible" in tags or not case["entities"]:
            stats = find_stats(a)
            checks["no_fabricated_figures"] = not stats or acknowledged
            if stats and not acknowledged:
                flags.append("states figures we do not hold: %s" % "; ".join(stats[:4]))
        else:
            # Check the figures against the database rather than against a tag.
            miss = uncorroborated(a, case["entities"])
            ok = acknowledged or len(miss) < 2
            checks["figures_corroborated"] = ok
            if miss:
                flags.append("%d figure(s) not found in our rows: %s"
                             % (len(miss), "; ".join(miss[:4])))

    if "impossible" in tags:
        ok = bool(has_any(a, REFUSAL))
        checks["refuses_false_premise"] = ok
        if not ok:
            flags.append("did not reject an impossible premise")

    if "bad_premise" in tags:
        ok = bool(has_any(a, CHALLENGE))
        checks["challenges_bad_logic"] = ok
        if not ok:
            flags.append("did not push back on flawed reasoning")

    if "ambiguous" in tags or "needs_context" in tags:
        # NFL-127 replied "I need the player and the negotiation context"
        # with four bullet questions and failed this check. Any answer that
        # actually asks something is clarifying, whatever words it uses.
        ok = bool(has_any(a, CLARIFY)) or "?" in a
        checks["clarifies_or_states_assumptions"] = ok
        if not ok:
            flags.append("answered an under-specified question without clarifying")

    if "sample_size" in tags or "projection" in tags:
        ok = bool(has_any(a, UNCERTAIN))
        checks["expresses_uncertainty"] = ok
        if not ok:
            flags.append("no uncertainty language on a small-sample or forecast question")

    if "causation" in tags:
        ok = bool(has_any(a, CAUSAL_HEDGE))
        checks["separates_cause_from_correlation"] = ok
        if not ok:
            flags.append("treated correlation as causation")

    if "two_sided" in tags:
        low = a.lower()
        ok = ("counter" in low or "against" in low or "team's" in low
              or "other side" in low or "downside" in low)
        checks["argues_both_sides"] = ok
        if not ok:
            flags.append("gave only one side of a two-sided question")

    # Only comparisons need every name present. "22.5 sacks in the 2021
    # regular season" answers "how many sacks did T.J. Watt have in 2021"
    # completely; demanding it repeat the name failed three correct answers.
    if len(case["entities"] or []) > 1:
        miss = [e for e in case["entities"] if e.lower() not in a.lower()]
        if miss and not has_any(a, REFUSAL):
            checks["mentions_expected_entities"] = False
            flags.append("never mentions: %s" % ", ".join(miss))
        elif miss:
            # Declined to answer, so not naming the player is a wording nit.
            flags.append("note: declined without naming %s" % ", ".join(miss))

    if not a.strip():
        checks["produced_an_answer"] = False
        flags.append("empty response")

    hard = ("no_fabricated_figures" in checks and not checks["no_fabricated_figures"]) \
        or ("refuses_false_premise" in checks and not checks["refuses_false_premise"])
    return checks, flags, hard


RUBRIC = """You are grading a sports analytics assistant called Rigorlytics.

Score the ANSWER against the QUESTION on each dimension, 0-100:
  intent_accuracy   (20%) did it understand what was actually asked
  entity_accuracy   (15%) correct player, team, season, position
  data_accuracy     (20%) are stated facts correct and supported
  analytical_logic  (20%) era adjustment, position-specific metrics, sample-size
                          awareness, appropriate comparables
  context_nuance    (10%) accounted for factors that materially change the answer
  hallucination_ctl (10%) avoided inventing facts, metrics or figures
  communication      (5%) clear, structured, appropriately detailed

Important grading rules:
- Declining to answer because data is unavailable is a PASS, not a failure.
  Score hallucination_ctl high when the assistant refuses to invent.
- Rejecting a false premise is correct behaviour and should score well.
- For an under-specified question, either asking for clarification or clearly
  stating the assumptions used is acceptable.
- Confident precision that the assistant cannot support is the worst failure.

TEST EXPECTATIONS: %s

QUESTION:
%s

ANSWER:
%s

Reply with ONLY a JSON object:
{"intent_accuracy":0,"entity_accuracy":0,"data_accuracy":0,"analytical_logic":0,
 "context_nuance":0,"hallucination_ctl":0,"communication":0,
 "verdict":"pass|borderline|fail","notes":"one sentence"}"""

WEIGHTS = dict(intent_accuracy=.20, entity_accuracy=.15, data_accuracy=.20,
               analytical_logic=.20, context_nuance=.10, hallucination_ctl=.10,
               communication=.05)


def judge(case, answer, model):
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = RUBRIC % (", ".join(case["tags"]) or "none",
                       case["prompt"] if isinstance(case["prompt"], str)
                       else " | ".join(case["prompt"]),
                       (answer or "")[:6000])
    msg = client.messages.create(model=model, max_tokens=400,
                                 messages=[{"role": "user", "content": prompt}])
    txt = msg.content[0].text.strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {"error": "judge returned no json", "raw": txt[:200]}
    d = json.loads(m.group(0))
    d["weighted"] = round(sum(float(d.get(k, 0)) * w for k, w in WEIGHTS.items()), 1)
    return d


# ------------------------------------------------------------------ run

def ask(case, target, live_url):
    prompts = case["prompt"] if isinstance(case["prompt"], list) else [case["prompt"]]
    turns = []
    for p in prompts:
        try:
            a = local_answer(p) if target == "local" else live_answer(p, live_url)
        except Exception as e:
            a = "[[ERROR: %s]]" % str(e)[:160]
        turns.append({"prompt": p, "answer": a})
    return turns


def run(cases, target, live_url, use_judge, judge_model, pause):
    results = []
    for i, case in enumerate(cases, 1):
        turns = ask(case, target, live_url)
        answer = "\n\n".join(t["answer"] for t in turns)
        # A transport error is not an answer. Grading one manufactures false
        # failures (an error page never mentions Jefferson) AND false passes
        # (a case with no applicable check falls through to clean), so it is
        # held out of the scored set rather than scored.
        # A local-target failure never carries the [[ERROR]] marker: the app
        # catches its own exception and returns a friendly sentence, which the
        # checks then grade as a real answer. That is how an out-of-credit run
        # reported eight hard failures on impossible-premise cases.
        APP_ERRORS = ("Rigorlytics hit an error processing",
                      "temporarily unable to reach its analysis engine",
                      "Rigorlytics is at capacity")
        errored = ("[[ERROR" in answer
                   or any(s in answer for s in APP_ERRORS))
        if errored:
            checks, flags, hard = {}, [], False
        else:
            checks, flags, hard = mechanical(case, answer)
        row = dict(case, target=target, turns=turns, answer=answer,
                   checks=checks, flags=flags, hard_fail=hard, errored=errored)
        row["mech_pass"] = (None if errored
                            else (all(checks.values()) if checks else None))
        if use_judge and not errored:
            try:
                row["judge"] = judge(case, answer, judge_model)
            except Exception as e:
                row["judge"] = {"error": str(e)[:160]}
        results.append(row)
        if errored:
            mark = "ERROR"
        else:
            mark = "HARD-FAIL" if hard else ("pass" if row["mech_pass"] in (True, None) else "fail")
        score = ""
        if row.get("judge", {}).get("weighted") is not None:
            score = "  judge=%s" % row["judge"]["weighted"]
        print("  %-9s %-9s %s%s" % (case["id"], mark, (flags[0] if flags else ""), score))
        time.sleep(pause)
    return results


def write_reports(results, target):
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    base = os.path.join(OUT_DIR, "results-%s" % target)

    with open(base + ".json", "w") as f:
        json.dump({"generated": stamp, "target": target, "results": results}, f, indent=2)

    with open(base + ".csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "severity", "tags", "prompt", "mech_pass",
                    "hard_fail", "flags", "judge_weighted", "judge_verdict",
                    "judge_notes", "answer"])
        for r in results:
            j = r.get("judge") or {}
            w.writerow([r["id"], CATEGORIES.get(r["category"], r["category"]),
                        r["severity"], ";".join(r["tags"]),
                        r["prompt"] if isinstance(r["prompt"], str) else " | ".join(r["prompt"]),
                        r["mech_pass"], r["hard_fail"], " | ".join(r["flags"]),
                        j.get("weighted"), j.get("verdict"), j.get("notes"),
                        (r["answer"] or "")[:4000]])

    hard = [r for r in results if r["hard_fail"]]
    soft = [r for r in results if not r["hard_fail"] and r["mech_pass"] is False]
    ok = [r for r in results if not r["hard_fail"] and r["mech_pass"] is not False]
    scored = [r["judge"]["weighted"] for r in results
              if isinstance(r.get("judge"), dict) and r["judge"].get("weighted") is not None]

    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    rows = []
    for r in sorted(results, key=lambda x: (not x["hard_fail"], x["id"])):
        j = r.get("judge") or {}
        cls = "hard" if r["hard_fail"] else ("soft" if r["mech_pass"] is False else "ok")
        rows.append(
            "<tr class='%s'><td class='id'>%s</td><td>%s</td><td>%s</td>"
            "<td class='q'>%s</td><td>%s</td><td class='f'>%s</td>"
            "<td class='a'>%s</td></tr>"
            % (cls, r["id"], esc(CATEGORIES.get(r["category"], "")), r["severity"],
               esc(r["prompt"] if isinstance(r["prompt"], str) else " | ".join(r["prompt"])),
               j.get("weighted", "-"), esc(" | ".join(r["flags"])),
               esc((r["answer"] or "")[:600])))

    html = """<!doctype html><meta charset="utf-8">
<title>Rigorlytics NFL UAT - %s</title>
<style>
 body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#111;background:#fff}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#666;margin-bottom:18px}
 .cards{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
 .card{border:1px solid #e3e3e3;border-radius:8px;padding:12px 16px;min-width:120px}
 .card b{display:block;font-size:24px} .card span{color:#666;font-size:12px}
 table{border-collapse:collapse;width:100%%;font-size:13px}
 th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;vertical-align:top}
 th{background:#fafafa;position:sticky;top:0}
 tr.hard{background:#fff2f2} tr.soft{background:#fffaf0}
 td.id{font-family:ui-monospace,monospace;white-space:nowrap}
 td.q{max-width:280px} td.a{max-width:420px;color:#444}
 td.f{max-width:220px;color:#a11}
</style>
<h1>Rigorlytics NFL UAT</h1>
<div class="sub">%s &middot; target: <b>%s</b> &middot; %d cases</div>
<div class="cards">
  <div class="card"><b>%d</b><span>hard failures</span></div>
  <div class="card"><b>%d</b><span>check failures</span></div>
  <div class="card"><b>%d</b><span>clean</span></div>
  <div class="card"><b>%s</b><span>mean judge score</span></div>
</div>
<table><tr><th>ID</th><th>Category</th><th>Sev</th><th>Prompt</th><th>Judge</th>
<th>Flags</th><th>Answer (truncated)</th></tr>
%s
</table>""" % (target, stamp, target, len(results), len(hard), len(soft), len(ok),
               (round(sum(scored) / len(scored), 1) if scored else "-"),
               "\n".join(rows))
    with open(base + ".html", "w") as f:
        f.write(html)

    print("\n%d cases | %d HARD failures | %d check failures | %d clean"
          % (len(results), len(hard), len(soft), len(ok)))
    if scored:
        print("mean judge score: %.1f" % (sum(scored) / len(scored)))
    if hard:
        print("\nHARD FAILURES (fabrication or accepted false premise):")
        for r in hard:
            print("  %s  %s" % (r["id"], r["flags"][0] if r["flags"] else ""))
    print("\nwrote %s.json / .csv / .html" % base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="local", choices=["local", "live"])
    ap.add_argument("--live-url", default="https://rigorlytics.net/api/ask")
    ap.add_argument("--phase1", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ids", default=None)
    ap.add_argument("--category", type=int, default=None)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--judge-model", default=os.getenv("UAT_JUDGE_MODEL", "claude-sonnet-4-5"))
    ap.add_argument("--pause", type=float, default=0.4)
    a = ap.parse_args()

    if a.ids:
        cases = by_ids([x.strip() for x in a.ids.split(",")])
    elif a.category:
        cases = [c for c in CASES if c["category"] == a.category]
    elif a.all:
        cases = CASES
    else:
        cases = by_ids(PHASE_1)
    if not cases:
        sys.exit("no cases selected")

    print("running %d cases against %s%s"
          % (len(cases), a.target, " with judge %s" % a.judge_model if a.judge else ""))
    results = run(cases, a.target, a.live_url, a.judge, a.judge_model, a.pause)
    write_reports(results, a.target)


if __name__ == "__main__":
    main()
