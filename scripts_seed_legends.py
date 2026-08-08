import sys
import requests
from concurrent.futures import ThreadPoolExecutor
from app.db import get_conn, get_league_id, log_ingestion

SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"
CORE = "https://sports.core.api.espn.com/v2/sports"

LEAGUE_UID = {"NBA": "l:46", "NFL": "l:28", "MLB": "l:10", "NHL": "l:90", "WNBA": "l:59"}
LEAGUE_PATH = {
    "NBA": "basketball/leagues/nba",
    "NFL": "football/leagues/nfl",
    "MLB": "baseball/leagues/mlb",
    "NHL": "hockey/leagues/nhl",
    "WNBA": "basketball/leagues/wnba",
}

NBA_LEGENDS = [
    "Michael Jordan", "Kobe Bryant", "Magic Johnson", "Larry Bird",
    "Kareem Abdul-Jabbar", "Shaquille O'Neal", "Tim Duncan", "Hakeem Olajuwon",
    "Wilt Chamberlain", "Bill Russell", "Oscar Robertson", "Jerry West",
    "Karl Malone", "John Stockton", "Charles Barkley", "Scottie Pippen",
    "David Robinson", "Patrick Ewing", "Dominique Wilkins", "Isiah Thomas",
    "Clyde Drexler", "Gary Payton", "Reggie Miller", "Allen Iverson",
    "Kevin Garnett", "Dirk Nowitzki", "Steve Nash", "Jason Kidd",
    "Tracy McGrady", "Vince Carter", "Ray Allen", "Paul Pierce",
    "Dwyane Wade", "Chris Bosh", "Carmelo Anthony", "Chris Paul",
    "Dwight Howard", "Pau Gasol", "Tony Parker", "Manu Ginobili",
    "Dennis Rodman", "Alonzo Mourning", "Chris Webber", "Grant Hill",
    "Penny Hardaway", "Shawn Kemp", "Mitch Richmond", "Glen Rice",
    "Rasheed Wallace", "Ben Wallace", "Elton Brand", "Baron Davis",
    "Gilbert Arenas", "Monta Ellis", "Joe Johnson", "Josh Smith",
    "Amare Stoudemire", "Steve Francis", "Stephon Marbury", "Antoine Walker",
    "Jermaine O'Neal", "Andrei Kirilenko", "Michael Redd", "Richard Hamilton",
    "Chauncey Billups", "Rip Hamilton", "Sam Cassell", "Jason Terry",
    "Peja Stojakovic", "Rashard Lewis", "Lamar Odom", "Andre Miller",
    "Zach Randolph", "David West", "Al Jefferson", "Tyson Chandler",
    "Kevin Love", "Blake Griffin", "Derrick Rose", "Rajon Rondo",
    "Deron Williams", "Brandon Roy", "Kevin Martin", "Danny Granger",
    "Julius Erving", "Moses Malone", "George Gervin", "Elgin Baylor",
    "Rick Barry", "Walt Frazier", "Willis Reed", "Dave Cowens",
    "Bob McAdoo", "Nate Archibald", "Earl Monroe", "Bob Lanier",
    "Artis Gilmore", "Dan Issel", "Alex English", "Adrian Dantley",
    "Bernard King", "James Worthy", "Kevin McHale", "Robert Parish",
    "Dennis Johnson", "Mark Aguirre", "Terry Cummings", "Sidney Moncrief",
]

NFL_LEGENDS = [
    "Jerry Rice", "Barry Sanders", "Joe Montana", "Emmitt Smith",
    "Walter Payton", "Lawrence Taylor", "Reggie White", "Deion Sanders",
    "John Elway", "Dan Marino", "Brett Favre", "Peyton Manning",
    "Tom Brady", "Randy Moss", "Terrell Owens", "Marvin Harrison",
    "LaDainian Tomlinson", "Adrian Peterson", "Ray Lewis", "Ed Reed",
    "Champ Bailey", "Bruce Smith", "Michael Strahan", "Warren Sapp",
    "Junior Seau", "Brian Urlacher", "Troy Polamalu", "Charles Woodson",
    "Steve Young", "Jim Kelly", "Warren Moon", "Kurt Warner",
    "Marshall Faulk", "Curtis Martin", "Jerome Bettis", "Eddie George",
    "Terrell Davis", "Priest Holmes", "Shaun Alexander", "Edgerrin James",
    "Isaac Bruce", "Torry Holt", "Cris Carter", "Tim Brown",
    "Andre Reed", "Sterling Sharpe", "Herman Moore", "Rod Smith",
    "Tony Gonzalez", "Shannon Sharpe", "Antonio Gates", "Jason Witten",
    "Anquan Boldin", "Larry Fitzgerald", "Steve Smith", "Hines Ward",
    "Reggie Wayne", "Andre Johnson", "Calvin Johnson", "Julio Jones",
    "Rob Gronkowski", "Drew Brees", "Aaron Rodgers", "Ben Roethlisberger",
    "Philip Rivers", "Eli Manning", "Michael Vick", "Donovan McNabb",
    "Ray Rice", "Frank Gore", "Steven Jackson", "Maurice Jones-Drew",
    "Clinton Portis", "Tiki Barber", "Corey Dillon", "Ricky Williams",
    "Jamal Lewis", "Fred Taylor", "Thomas Jones", "Willis McGahee",
    "Derrick Brooks", "Zach Thomas", "Takeo Spikes", "London Fletcher",
    "Julius Peppers", "Dwight Freeney", "Jared Allen", "John Randle",
    "Ty Law", "Darrelle Revis", "Richard Sherman", "Patrick Peterson",
    "Ronnie Lott", "Rod Woodson", "Darren Sharper", "Brian Dawkins",
]

MLB_LEGENDS = [
    "Babe Ruth", "Willie Mays", "Hank Aaron", "Ted Williams",
    "Lou Gehrig", "Ty Cobb", "Mickey Mantle", "Stan Musial",
    "Joe DiMaggio", "Jackie Robinson", "Roberto Clemente", "Sandy Koufax",
    "Bob Gibson", "Nolan Ryan", "Tom Seaver", "Steve Carlton",
    "Cal Ripken Jr.", "Tony Gwynn", "Wade Boggs", "Rickey Henderson",
    "Barry Bonds", "Ken Griffey Jr.", "Greg Maddux", "Randy Johnson",
    "Pedro Martinez", "Roger Clemens", "Mariano Rivera", "Derek Jeter",
    "Alex Rodriguez", "Albert Pujols", "Ichiro Suzuki", "Chipper Jones",
    "Frank Thomas", "Jeff Bagwell", "Craig Biggio", "Mike Piazza",
    "Ivan Rodriguez", "Vladimir Guerrero", "Manny Ramirez", "David Ortiz",
    "Jim Thome", "Sammy Sosa", "Mark McGwire", "Rafael Palmeiro",
    "Roberto Alomar", "Ryne Sandberg", "Ozzie Smith", "Barry Larkin",
]

NHL_LEGENDS = [
    "Wayne Gretzky", "Mario Lemieux", "Gordie Howe", "Bobby Orr",
    "Jaromir Jagr", "Mark Messier", "Steve Yzerman", "Ray Bourque",
    "Patrick Roy", "Martin Brodeur", "Dominik Hasek", "Joe Sakic",
    "Peter Forsberg", "Brett Hull", "Teemu Selanne", "Jarome Iginla",
    "Nicklas Lidstrom", "Chris Chelios", "Scott Stevens", "Paul Coffey",
    "Sidney Crosby", "Alex Ovechkin", "Evgeni Malkin", "Pavel Datsyuk",
    "Henrik Lundqvist", "Zdeno Chara", "Daniel Sedin", "Henrik Sedin",
]

WNBA_LEGENDS = [
    "Diana Taurasi", "Sue Bird", "Lisa Leslie", "Sheryl Swoopes",
    "Tamika Catchings", "Maya Moore", "Candace Parker", "Cynthia Cooper",
    "Lauren Jackson", "Tina Thompson", "Rebecca Lobo", "Swin Cash",
    "Seimone Augustus", "Sylvia Fowles", "Elena Delle Donne", "Brittney Griner",
]

LEGENDS = {
    "NBA": NBA_LEGENDS,
    "NFL": NFL_LEGENDS,
    "MLB": MLB_LEGENDS,
    "NHL": NHL_LEGENDS,
    "WNBA": WNBA_LEGENDS,
}


def find_and_fetch(args):
    """Search for a name, verify it has stats, return player dict."""
    name, code = args
    uid_frag = LEAGUE_UID[code]
    path = LEAGUE_PATH[code]
    try:
        r = requests.get(SEARCH_URL, params={"query": name, "limit": 10}, timeout=15)
        data = r.json()
        target = name.strip().lower()

        candidates = []
        for res in data.get("results", []):
            if res.get("type") != "player":
                continue
            for c in res.get("contents", []):
                uid = c.get("uid", "")
                if "a:" not in uid:
                    continue
                aid = uid.split("a:")[-1]
                dn = c.get("displayName", "")
                exact = dn.strip().lower() == target
                in_league = uid_frag in uid
                leagueless = "l:" not in uid
                score = (0 if exact else 3) + (0 if (in_league or leagueless) else 5)
                candidates.append((score, aid, dn, c.get("subtitle", "")))

        candidates.sort(key=lambda x: x[0])

        for score, aid, dn, sub in candidates[:4]:
            for probe in (2024, 2015, 2005, 1998, 1990, 1985, 1975):
                u = f"{CORE}/{path}/seasons/{probe}/types/2/athletes/{aid}/statistics"
                pr = requests.get(u, timeout=12)
                if pr.status_code == 200:
                    return {"external_id": aid, "full_name": dn,
                            "position": None, "active": False, "query": name}
        return None
    except Exception:
        return None


def seed(code):
    lid = get_league_id(code)
    names = LEGENDS.get(code, [])
    print(f"[{code}] resolving {len(names)} legends...")

    found = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for res in pool.map(find_and_fetch, [(n, code) for n in names]):
            if res:
                found.append(res)

    missing = len(names) - len(found)
    rows = [(lid, p["external_id"], p["full_name"], p["position"], False)
            for p in found]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO players (league_id, external_id, full_name, position, active)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (league_id, external_id) DO UPDATE SET
                       full_name = EXCLUDED.full_name,
                       updated_at = now()""",
                rows,
            )

    log_ingestion("espn-search", "legends", lid, len(rows), "success")
    print(f"[{code}] stored {len(rows)}, missing {missing}")
    return len(rows)


if __name__ == "__main__":
    target = sys.argv[1].upper() if len(sys.argv) > 1 else None
    codes = [target] if target else list(LEGENDS.keys())
    for c in codes:
        seed(c)

    print()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT l.code, count(*) AS n
                           FROM players p JOIN leagues l ON l.id = p.league_id
                           GROUP BY l.code ORDER BY l.code""")
            for r in cur.fetchall():
                print(f"  {r['code']:5} {r['n']}")
