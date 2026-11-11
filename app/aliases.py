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


# ------------------------------------------------------- one-word names
# find_players() tries an exact match, then a PREFIX match against the
# full name. A one-word name therefore matches a player's FIRST name.
# "Jordan" found Jordan Poyer, a Bills safety, and never considered
# Michael Jordan -- asked "Jordan vs LeBron career stats", the site
# compared LeBron James to an NFL defensive back. "LeBron" worked only by
# accident: no other player's name starts with it.
#
# Rule for adding here: the one-word form must be unambiguous across every
# league in the database. Deliberately NOT included -- "malone" (Karl,
# Moses), "russell" (Bill, Westbrook, D'Angelo), "barkley" (Charles,
# Saquon), "manning" (Peyton, Eli), "jackson" (Lamar, Bo, DeSean),
# "allen" (Josh Allen, Allen Iverson), "aaron" (Hank Aaron, Aaron Rodgers,
# Aaron Judge), "kelce" (Travis, Jason), "matthews" (Auston, Clay).
ALIASES.update({
    "jordan": "Michael Jordan",
    "lebron": "LeBron James",
    "kobe": "Kobe Bryant",
    "curry": "Stephen Curry",
    "harden": "James Harden",
    "durant": "Kevin Durant",
    "westbrook": "Russell Westbrook",
    "iverson": "Allen Iverson",
    "duncan": "Tim Duncan",
    "pippen": "Scottie Pippen",
    "rodman": "Dennis Rodman",
    "ewing": "Patrick Ewing",
    "garnett": "Kevin Garnett",
    "nowitzki": "Dirk Nowitzki",
    "carmelo": "Carmelo Anthony",
    "olajuwon": "Hakeem Olajuwon",
    "kyrie": "Kyrie Irving",
    "zion": "Zion Williamson",
    "wilt": "Wilt Chamberlain",
    "chamberlain": "Wilt Chamberlain",

    "mahomes": "Patrick Mahomes",
    "brady": "Tom Brady",
    "rodgers": "Aaron Rodgers",
    "favre": "Brett Favre",
    "montana": "Joe Montana",
    "elway": "John Elway",
    "marino": "Dan Marino",
    "lamar": "Lamar Jackson",
    "burrow": "Joe Burrow",
    "herbert": "Justin Herbert",
    "jefferson": "Justin Jefferson",
    "saquon": "Saquon Barkley",
    "kamara": "Alvin Kamara",
    "tyreek": "Tyreek Hill",

    "trout": "Mike Trout",
    "pujols": "Albert Pujols",
    "jeter": "Derek Jeter",
    "bonds": "Barry Bonds",
    "mantle": "Mickey Mantle",
    "gehrig": "Lou Gehrig",
    "cobb": "Ty Cobb",
    "clemens": "Roger Clemens",
    "maddux": "Greg Maddux",
    "kershaw": "Clayton Kershaw",
    "verlander": "Justin Verlander",

    "gretzky": "Wayne Gretzky",
    "ovechkin": "Alex Ovechkin",
    "ovi": "Alex Ovechkin",
    "crosby": "Sidney Crosby",
    "mcdavid": "Connor McDavid",
    "lemieux": "Mario Lemieux",
})
