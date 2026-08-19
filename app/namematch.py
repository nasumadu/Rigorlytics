"""
Rigorlytics - tolerant name resolution.

"Jamaar Chase" matches neither an exact lookup nor a prefix LIKE against
"Ja'Marr Chase", so the retrieval returns nothing and the model correctly
reports it holds no such player. Answering "I do not have him" because two
letters were transposed is the worst failure this lookup can produce: the
data is there, and the user is told it is not.

This runs only after the strict passes have failed, and only against names
already narrowed by surname, so a wrong guess has a small blast radius.
"""

import difflib
import re
import unicodedata

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
THRESHOLD = 0.82


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9 ]+", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _core(s):
    return [t for t in norm(s).split() if t not in SUFFIXES]


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def score(query, candidate):
    q, c = _core(query), _core(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    best = _ratio(" ".join(q), " ".join(c))
    # A shared surname carries most of the signal. "Jamaar Chase" and "Ja'Marr
    # Chase" agree on the surname and differ by two letters in the given name:
    # that is a typo. "Jaylen Jefferson" against "Justin Jefferson" also shares
    # a surname but the given names are genuinely different, and the weighting
    # below leaves it under the threshold.
    if q[-1] == c[-1]:
        if len(q) > 1 and len(c) > 1:
            given = _ratio(" ".join(q[:-1]), " ".join(c[:-1]))
        else:
            given = 0.6
        best = max(best, 0.55 + 0.45 * given)
    return best


def rank_names(query, candidates, key=None, threshold=THRESHOLD, limit=5):
    """Candidates above the threshold, closest first. Empty when none qualify."""
    if key is None:
        key = lambda x: x
    scored = []
    for cand in candidates:
        s = score(query, key(cand))
        if s >= threshold:
            scored.append((s, key(cand), cand))
    scored.sort(key=lambda t: (-t[0], len(t[1])))
    return [c for _, _, c in scored[:limit]]
