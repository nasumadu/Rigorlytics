"""Unified player search: database first, live ESPN as fallback."""

from concurrent.futures import ThreadPoolExecutor

from app.players import extract_names, get_player_block as espn_block
from app.player_db import lookup_from_db


def resolve(name):
    """Try the database, then fall back to a live ESPN lookup."""
    try:
        block = lookup_from_db(name)
        if block:
            return block
    except Exception:
        pass
    try:
        return espn_block(name)
    except Exception:
        return ""


def search_players(question):
    """Extract names from a question and return combined stat context."""
    names = extract_names(question)
    if not names:
        return ""
    out = ""
    with ThreadPoolExecutor(max_workers=4) as pool:
        for block in pool.map(resolve, names):
            if block:
                out += block
    return out
