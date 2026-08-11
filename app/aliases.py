"""Name aliases for common nicknames and alternate spellings."""

ALIASES = {
    # NFL
    "michael vick": "Mike Vick",
    "mike vick": "Mike Vick",
    "ochocinco": "Chad Johnson",
    "megatron": "Calvin Johnson",
    "gronk": "Rob Gronkowski",
    "ad": "Anthony Davis",
    "cmc": "Christian McCaffrey",
    "tb12": "Tom Brady",

    # NBA
    "shaq": "Shaquille O'Neal",
    "magic": "Magic Johnson",
    "magic johnson": "Magic Johnson",
    "steph": "Stephen Curry",
    "steph curry": "Stephen Curry",
    "chef curry": "Stephen Curry",
    "cp3": "Chris Paul",
    "ai": "Allen Iverson",
    "the answer": "Allen Iverson",
    "wemby": "Victor Wembanyama",
    "sga": "Shai Gilgeous-Alexander",
    "kd": "Kevin Durant",
    "kg": "Kevin Garnett",
    "dirk": "Dirk Nowitzki",
    "manu": "Manu Ginobili",
    "melo": "Carmelo Anthony",
    "dbook": "Devin Booker",
    "bron": "LeBron James",
    "king james": "LeBron James",
    "the beard": "James Harden",
    "greek freak": "Giannis Antetokounmpo",
    "giannis": "Giannis Antetokounmpo",
    "luka": "Luka Doncic",
    "jokic": "Nikola Jokic",
    "the joker": "Nikola Jokic",
    "embiid": "Joel Embiid",
    "flash": "Dwyane Wade",
    "dwade": "Dwyane Wade",
    "d wade": "Dwyane Wade",
    "mj": "Michael Jordan",
    "air jordan": "Michael Jordan",
    "the mailman": "Karl Malone",
    "the dream": "Hakeem Olajuwon",
    "hakeem": "Hakeem Olajuwon",
    "kareem": "Kareem Abdul-Jabbar",
    "pip": "Scottie Pippen",
    "worm": "Dennis Rodman",

    # MLB
    "big papi": "David Ortiz",
    "the kid": "Ken Griffey Jr.",
    "griffey": "Ken Griffey Jr.",
    "a rod": "Alex Rodriguez",
    "arod": "Alex Rodriguez",
    "the babe": "Babe Ruth",
    "ohtani": "Shohei Ohtani",
    "judge": "Aaron Judge",

    # NHL
    "the great one": "Wayne Gretzky",
    "gretzky": "Wayne Gretzky",
    "super mario": "Mario Lemieux",
    "ovi": "Alex Ovechkin",
    "sid the kid": "Sidney Crosby",
    "mcdavid": "Connor McDavid",
}


def resolve_alias(name):
    """Return the canonical name if an alias exists, else the original."""
    key = name.strip().lower().replace(".", "").replace("'", "'")
    return ALIASES.get(key, name)
