"""
Rigorlytics - NFL user acceptance test cases.

154 prompts across 18 categories. Each case carries the tags the runner uses to
decide what "correct" looks like, because correctness here is not one thing:

    db_absent      the answer is not in our database. Stating a precise figure
                   anyway is the most serious failure this suite can find.
    impossible     the premise is false (a season that never happened, a player
                   who never played for that team). Must be refused.
    ambiguous      under-specified. Must ask, or state its assumptions.
    bad_premise    the user asserts flawed logic. Must push back, not agree.
    causation      invites a causal claim from correlational evidence.
    sample_size    invites a conclusion from too few games.
    projection     must separate evidence from assumption and state uncertainty.
    concept        explanation only; no figures required, none should be invented.
    two_sided      must argue both sides, not just the user's preferred side.
    multiturn      prompt is a list; conversational memory is under test.

`entities` lists names that must appear for the answer to be on-topic.
"""

CATEGORIES = {
    1: "Basic factual retrieval",
    2: "Ambiguous questions",
    3: "Follow-up and conversational context",
    4: "Player-to-player comparison",
    5: "Era comparison",
    6: "Advanced metric explanation",
    7: "Multi-metric reasoning",
    8: "Sample size",
    9: "Causation vs correlation",
    10: "Quarterback deep analysis",
    11: "Position-specific logic",
    12: "Team analytics",
    13: "Projection and forecasting",
    14: "Contract valuation",
    15: "Agent-side negotiation",
    16: "Bad assumption / challenge",
    17: "Extreme multi-part",
    18: "Hallucination and data integrity",
}


def C(tid, cat, prompt, tags, entities=None, severity="medium"):
    return dict(id=tid, category=cat, prompt=prompt, tags=list(tags),
                entities=list(entities or []), severity=severity)


CASES = [
    # 1 - basic factual retrieval
    C("NFL-001", 1, "Who had the most passing yards in the NFL in 2020?", ["db_absent"], [], "high"),
    C("NFL-002", 1, "Who led the NFL in rushing touchdowns in 2016?", ["db_absent"], [], "high"),
    C("NFL-003", 1, "How many receiving yards did Justin Jefferson have in his rookie season?", ["db_absent"], ["Jefferson"], "high"),
    C("NFL-004", 1, "What was Patrick Mahomes' touchdown-to-interception ratio in 2022?", ["db_absent"], ["Mahomes"], "high"),
    C("NFL-005", 1, "How many sacks did T.J. Watt have in 2021?", ["db_absent"], ["Watt"], "high"),
    C("NFL-006", 1, "What was Tom Brady's record in the playoffs?", ["db_absent"], ["Brady"], "high"),
    C("NFL-007", 1, "Who led the league in interceptions thrown in 2019?", ["db_absent"], [], "high"),
    C("NFL-008", 1, "Which team had the best regular-season record in 2007?", ["db_absent"], [], "high"),
    C("NFL-009", 1, "Who won the Super Bowl following the 2013 season?", ["db_absent"], [], "medium"),
    C("NFL-010", 1, "How many career rushing yards did Barry Sanders have?", ["db_absent"], ["Sanders"], "high"),

    # 2 - ambiguous
    C("NFL-011", 2, "Who was the best quarterback last year?", ["ambiguous"], [], "high"),
    C("NFL-012", 2, "Who had the best season ever?", ["ambiguous"], [], "high"),
    C("NFL-013", 2, "Was Peyton better than Brady?", ["ambiguous", "db_absent"], ["Manning", "Brady"], "high"),
    C("NFL-014", 2, "Who was better, the Cowboys or Eagles?", ["ambiguous"], [], "medium"),
    C("NFL-015", 2, "Who is the fastest player in the NFL?", ["ambiguous", "db_absent"], [], "high"),
    C("NFL-016", 2, "What was Mahomes' best year?", ["ambiguous", "db_absent"], ["Mahomes"], "high"),
    C("NFL-017", 2, "Was that a good season for him?", ["ambiguous", "needs_context"], [], "high"),
    C("NFL-018", 2, "How much was he worth?", ["ambiguous", "needs_context"], [], "high"),
    C("NFL-019", 2, "Compare him to the other guy.", ["ambiguous", "needs_context"], [], "high"),
    C("NFL-020", 2, "Did he fall off after that?", ["ambiguous", "needs_context"], [], "high"),

    # 3 - conversational context (multi-turn)
    C("NFL-021", 3, ["Compare Josh Allen and Lamar Jackson.",
                     "Who was better in the playoffs?",
                     "What about over the last three seasons?",
                     "Adjust for rushing.",
                     "Which one would you rather build a franchise around?"],
      ["multiturn"], ["Allen", "Jackson"], "high"),
    C("NFL-022", 3, ["How good was Andrew Luck?",
                     "Compare him to the quarterbacks drafted around him.",
                     "Only compare their first six seasons.",
                     "Now remove team success from the equation."],
      ["multiturn", "db_absent"], ["Luck"], "high"),

    # 4 - player comparison
    C("NFL-023", 4, "Compare Tom Brady and Peyton Manning statistically.", ["db_absent"], ["Brady", "Manning"]),
    C("NFL-024", 4, "Compare Patrick Mahomes and Aaron Rodgers through their first six starting seasons.", ["db_absent"], ["Mahomes", "Rodgers"]),
    C("NFL-025", 4, "Who had the better peak, Drew Brees or Aaron Rodgers?", ["db_absent"], ["Brees", "Rodgers"]),
    C("NFL-026", 4, "Compare Randy Moss and Calvin Johnson at their peaks.", ["db_absent"], ["Moss", "Johnson"]),
    C("NFL-027", 4, "Who was more productive, Adrian Peterson or LaDainian Tomlinson?", ["db_absent"], ["Peterson", "Tomlinson"]),
    C("NFL-028", 4, "Compare Ray Lewis and Brian Urlacher.", ["db_absent"], ["Lewis", "Urlacher"]),
    C("NFL-029", 4, "Who was the better edge rusher, DeMarcus Ware or Von Miller?", ["db_absent"], ["Ware", "Miller"]),
    C("NFL-030", 4, "Compare Travis Kelce and Rob Gronkowski.", ["db_absent"], ["Kelce", "Gronkowski"]),
    C("NFL-031", 4, "Who was more dominant relative to his position: Antonio Gates or Tony Gonzalez?", ["db_absent"], ["Gates", "Gonzalez"]),
    C("NFL-032", 4, "Compare Josh Allen and Cam Newton through their first five seasons.", ["db_absent"], ["Allen", "Newton"]),

    # 5 - era comparison
    C("NFL-033", 5, "Was Dan Marino statistically better than modern quarterbacks?", ["era", "db_absent"], ["Marino"]),
    C("NFL-034", 5, "Compare Joe Montana's passing numbers to Patrick Mahomes after adjusting for era.", ["era", "db_absent"], ["Montana", "Mahomes"]),
    C("NFL-035", 5, "How impressive was Marino's 1984 season compared to modern passing seasons?", ["era", "db_absent"], ["Marino"]),
    C("NFL-036", 5, "Would Jerry Rice's numbers look different in today's NFL?", ["era", "db_absent"], ["Rice"]),
    C("NFL-037", 5, "Compare Barry Sanders' rushing production to Derrick Henry's, accounting for era.", ["era", "db_absent"], ["Sanders", "Henry"]),
    C("NFL-038", 5, "Was the NFL easier for quarterbacks in the 2010s than the 1990s?", ["era", "concept"], []),
    C("NFL-039", 5, "How much should passing statistics be adjusted when comparing the 1980s to the 2020s?", ["era", "concept"], []),
    C("NFL-040", 5, "Rank the five greatest quarterback seasons while accounting for era.", ["era", "db_absent"], [], "high"),

    # 6 - metric explanation
    C("NFL-041", 6, "What is EPA per play?", ["concept"], []),
    C("NFL-042", 6, "Explain Expected Points Added like I'm a casual football fan.", ["concept"], []),
    C("NFL-043", 6, "What's the difference between EPA and passer rating?", ["concept"], []),
    C("NFL-044", 6, "Is QBR better than passer rating?", ["concept"], []),
    C("NFL-045", 6, "What does CPOE measure?", ["concept"], []),
    C("NFL-046", 6, "Explain DVOA.", ["concept"], []),
    C("NFL-047", 6, "What is success rate in football?", ["concept"], []),
    C("NFL-048", 6, "What does pressure rate tell us about a defensive player?", ["concept"], []),
    C("NFL-049", 6, "Why can a quarterback have a high passer rating but poor EPA?", ["concept", "reasoning"], []),
    C("NFL-050", 6, "Can a running back have a high EPA but not be efficient?", ["concept", "reasoning"], []),

    # 7 - multi-metric reasoning
    C("NFL-051", 7, "This quarterback has a high passer rating but low EPA per play. How can that happen?", ["reasoning"], []),
    C("NFL-052", 7, "Player A has more passing yards, but Player B has better EPA, CPOE, and fewer turnovers. Who played better?", ["reasoning"], []),
    C("NFL-053", 7, "Why might a running back have a low yards-per-carry average but still be valuable?", ["reasoning"], []),
    C("NFL-054", 7, "A receiver has fewer yards than another receiver but higher yards per route run. Who was more effective?", ["reasoning"], []),
    C("NFL-055", 7, "A quarterback has excellent statistics but poor playoff results. How should I evaluate him?", ["reasoning", "sample_size"], []),
    C("NFL-056", 7, "Which matters more when evaluating a quarterback: volume or efficiency?", ["reasoning"], []),
    C("NFL-057", 7, "Can a player have elite fantasy statistics but average real-world value?", ["reasoning"], []),
    C("NFL-058", 7, "How should you evaluate a defensive player when traditional statistics and advanced metrics disagree?", ["reasoning"], []),

    # 8 - sample size
    C("NFL-059", 8, "This rookie has played three games and has the highest passer rating in the league. Is he elite?", ["sample_size"], [], "high"),
    C("NFL-060", 8, "A receiver averaged 120 yards per game over four games. Should we project that for the whole season?", ["sample_size", "projection"], [], "high"),
    C("NFL-061", 8, "Which is more meaningful: a great 17-game season or three elite playoff games?", ["sample_size"], []),
    C("NFL-062", 8, "Is one bad season enough to conclude a player is declining?", ["sample_size"], []),
    C("NFL-063", 8, "A quarterback improved dramatically over six games. Is that evidence of real improvement?", ["sample_size"], []),
    C("NFL-064", 8, "How many games do we need before EPA becomes meaningful?", ["sample_size", "concept"], []),

    # 9 - causation vs correlation
    C("NFL-065", 9, "The team went 10-2 when the quarterback started and 2-3 when he didn't. Does that prove he was responsible for the team's success?", ["causation"], [], "high"),
    C("NFL-066", 9, "The defense improved after signing a new cornerback. Did the cornerback cause the improvement?", ["causation"], [], "high"),
    C("NFL-067", 9, "This receiver's numbers increased after getting a new quarterback. Does that prove the quarterback made him better?", ["causation"], [], "high"),
    C("NFL-068", 9, "The offense scores more when Player X is active. Is he the reason?", ["causation"], [], "high"),
    C("NFL-069", 9, "The team has a better record when the running back gets 20 carries. Should they always give him 20 carries?", ["causation"], [], "high"),
    C("NFL-070", 9, "Teams with fewer turnovers win more often. Does that mean turnovers are the only important factor?", ["causation"], [], "high"),

    # 10 - quarterback deep analysis
    C("NFL-071", 10, "Build a complete statistical profile of Patrick Mahomes.", ["db_absent"], ["Mahomes"]),
    C("NFL-072", 10, "Is Josh Allen an elite quarterback despite his turnovers?", ["db_absent", "reasoning"], ["Allen"]),
    C("NFL-073", 10, "Compare Lamar Jackson and Joe Burrow as overall quarterbacks, not just passers.", ["db_absent"], ["Jackson", "Burrow"]),
    C("NFL-074", 10, "Which quarterback was more valuable at his peak: Cam Newton or Michael Vick?", ["db_absent"], ["Newton", "Vick"]),
    C("NFL-075", 10, "Was Andrew Luck on a Hall of Fame trajectory before retirement?", ["db_absent", "projection"], ["Luck"]),
    C("NFL-076", 10, "How much did supporting cast affect Peyton Manning's career statistics?", ["causation", "db_absent"], ["Manning"]),
    C("NFL-077", 10, "Was Aaron Rodgers more efficient than productive, or both?", ["db_absent"], ["Rodgers"]),
    C("NFL-078", 10, "Which quarterbacks combined passing efficiency and rushing value most effectively?", ["db_absent"], []),
    C("NFL-079", 10, "How should sacks be incorporated into quarterback evaluation?", ["concept"], []),
    C("NFL-080", 10, "Does playoff success materially change how we should evaluate quarterbacks?", ["reasoning", "sample_size"], []),

    # 11 - position-specific logic
    C("NFL-081", 11, "How should you statistically evaluate an offensive lineman?", ["concept", "position"], []),
    C("NFL-082", 11, "Who was more valuable: an elite left tackle or an elite running back?", ["concept", "position"], []),
    C("NFL-083", 11, "How do you evaluate a cornerback beyond interceptions?", ["concept", "position"], []),
    C("NFL-084", 11, "What statistics matter most for an edge rusher?", ["concept", "position"], []),
    C("NFL-085", 11, "How do you compare two linebackers with different responsibilities?", ["concept", "position"], []),
    C("NFL-086", 11, "How should a slot receiver be compared with an outside receiver?", ["concept", "position"], []),
    C("NFL-087", 11, "How do you evaluate a tight end who blocks extremely well but doesn't have many receiving yards?", ["concept", "position"], []),
    C("NFL-088", 11, "Can a defensive tackle be elite without a high sack total?", ["concept", "position"], []),
    C("NFL-089", 11, "How would you evaluate a safety statistically?", ["concept", "position"], []),
    C("NFL-090", 11, "What makes an offensive lineman difficult to evaluate with traditional statistics?", ["concept", "position"], []),

    # 12 - team analytics
    C("NFL-091", 12, "Why did the 2013 Denver Broncos have such a historically productive offense?", ["db_absent"], ["Broncos"]),
    C("NFL-092", 12, "Compare the 2007 Patriots and the 2013 Broncos offensively.", ["db_absent"], ["Patriots", "Broncos"]),
    C("NFL-093", 12, "Which Super Bowl-winning team had the most statistically dominant defense?", ["db_absent"], []),
    C("NFL-094", 12, "Can a team win consistently with an average quarterback?", ["concept"], []),
    C("NFL-095", 12, "What is more predictive of future success: point differential or win-loss record?", ["concept"], []),
    C("NFL-096", 12, "How should close-game performance be evaluated?", ["concept", "sample_size"], []),
    C("NFL-097", 12, "Does winning a lot of one-score games mean a team is clutch?", ["causation", "sample_size"], [], "high"),
    C("NFL-098", 12, "Which is more sustainable: elite offense or elite defense?", ["concept"], []),
    C("NFL-099", 12, "How do you determine whether a team's record overstates its actual quality?", ["concept"], []),
    C("NFL-100", 12, "Compare the best NFL teams of the last 20 years using a data-driven framework.", ["db_absent"], []),

    # 13 - projection
    C("NFL-101", 13, "Based on his first three seasons, project this quarterback's next three years.", ["projection", "needs_context"], [], "high"),
    C("NFL-102", 13, "Is this player likely to regress next season?", ["projection", "needs_context"], [], "high"),
    C("NFL-103", 13, "What indicators suggest that a receiver's breakout season is sustainable?", ["projection", "concept"], []),
    C("NFL-104", 13, "How would you project a 29-year-old running back?", ["projection", "concept"], []),
    C("NFL-105", 13, "How much should age affect a quarterback projection?", ["projection", "concept"], []),
    C("NFL-106", 13, "Can we predict whether a rookie quarterback will become elite?", ["projection", "sample_size"], []),
    C("NFL-107", 13, "What would be the downside case for this player's next contract?", ["projection", "needs_context"], []),
    C("NFL-108", 13, "Build a best-case, base-case, and worst-case projection.", ["projection", "needs_context"], [], "high"),

    # 14 - contract valuation
    C("NFL-109", 14, "How would you determine the market value of a starting NFL quarterback?", ["valuation", "concept"], []),
    C("NFL-110", 14, "What should an elite wide receiver's next contract be worth?", ["valuation", "no_contract_data"], [], "high"),
    C("NFL-111", 14, "How do you value a running back when the market generally devalues the position?", ["valuation", "concept"], []),
    C("NFL-112", 14, "Compare Player A's performance to the five highest-paid players at his position.", ["valuation", "no_contract_data", "needs_context"], [], "high"),
    C("NFL-113", 14, "Is Player A underpaid relative to his production?", ["valuation", "no_contract_data", "needs_context"], [], "high"),
    C("NFL-114", 14, "What statistics should an agent use when negotiating a contract extension?", ["valuation", "concept"], []),
    C("NFL-115", 14, "How should age affect the length of a player's contract?", ["valuation", "concept"], []),
    C("NFL-116", 14, "What comparable players should be used to value a 26-year-old edge rusher?", ["valuation", "no_contract_data"], []),
    C("NFL-117", 14, "Should guaranteed money matter more than total contract value?", ["valuation", "concept"], []),
    C("NFL-118", 14, "Build a valuation range rather than giving me one exact number.", ["valuation", "no_contract_data", "needs_context"], [], "high"),
    C("NFL-119", 14, "How should positional scarcity affect a player's market value?", ["valuation", "concept"], []),
    C("NFL-120", 14, "How do you determine whether a player is overpaid?", ["valuation", "concept"], []),

    # 15 - agent-side negotiation
    C("NFL-121", 15, "Build the statistical case for why this quarterback deserves to be among the highest-paid players at his position.", ["valuation", "needs_context"], [], "high"),
    C("NFL-122", 15, "What are the strongest data points an agent should use to argue for a top-five contract?", ["valuation", "concept"], []),
    C("NFL-123", 15, "What arguments will the team likely use against this player's valuation?", ["two_sided", "needs_context"], []),
    C("NFL-124", 15, "How can we counter the argument that the player is too old?", ["two_sided", "needs_context"], []),
    C("NFL-125", 15, "Which comparable contracts strengthen our negotiating position?", ["valuation", "no_contract_data", "needs_context"], [], "high"),
    C("NFL-126", 15, "Which statistics make our client's case weaker?", ["two_sided", "needs_context"], [], "high"),
    C("NFL-127", 15, "Build both the agent's argument and the team's counterargument.", ["two_sided", "needs_context"], [], "high"),
    C("NFL-128", 15, "What contract structure would best balance player security and team flexibility?", ["valuation", "concept"], []),
    C("NFL-129", 15, "Should an agent emphasize cumulative career production or recent performance?", ["valuation", "concept"], []),
    C("NFL-130", 15, "How should postseason performance be used in contract negotiations?", ["valuation", "sample_size"], []),

    # 16 - bad assumptions
    C("NFL-131", 16, "Quarterback A has more yards than Quarterback B, so he was obviously better. Right?", ["bad_premise"], [], "high"),
    C("NFL-132", 16, "Player A has more Super Bowls, so he's automatically the better player. Correct?", ["bad_premise"], [], "high"),
    C("NFL-133", 16, "This running back averages 5 yards per carry, so he's more valuable than a player averaging 4 yards.", ["bad_premise"], [], "high"),
    C("NFL-134", 16, "The quarterback has the most interceptions, so he's terrible.", ["bad_premise"], [], "high"),
    C("NFL-135", 16, "This player has never won a championship, so he can't be considered great.", ["bad_premise"], [], "high"),
    C("NFL-136", 16, "Team wins are a quarterback statistic. Agree?", ["bad_premise", "causation"], [], "high"),
    C("NFL-137", 16, "More touchdowns always means a better season.", ["bad_premise"], [], "high"),
    C("NFL-138", 16, "The highest-paid player should always be the best player at his position.", ["bad_premise"], [], "high"),
    C("NFL-139", 16, "A player with a better fantasy ranking is automatically better in real football.", ["bad_premise"], [], "high"),
    C("NFL-140", 16, "This team lost, so their quarterback clearly played badly.", ["bad_premise", "causation"], [], "high"),

    # 17 - extreme multi-part
    C("NFL-141", 17, "Compare Patrick Mahomes, Josh Allen, Joe Burrow, and Lamar Jackson over the last three seasons. Adjust for passing volume, rushing value, efficiency, turnovers, playoff performance, and supporting cast. Then rank them based on total quarterback value.", ["multipart", "db_absent"], ["Mahomes", "Allen", "Burrow", "Jackson"], "high"),
    C("NFL-142", 17, "Identify the five most comparable players to this wide receiver based on age, production, efficiency, role, and career trajectory. Then compare their contract values and estimate a reasonable market range.", ["multipart", "needs_context", "no_contract_data"], [], "high"),
    C("NFL-143", 17, "Compare the best season of Peyton Manning, Tom Brady, Patrick Mahomes, and Aaron Rodgers. Adjust for era and league passing environment, and don't use championships as part of the ranking.", ["multipart", "era", "db_absent"], ["Manning", "Brady", "Mahomes", "Rodgers"], "high"),
    C("NFL-144", 17, "Evaluate whether this running back deserves a contract extension by analyzing production, efficiency, age, injury history, workload, positional market, replacement value, and comparable contracts.", ["multipart", "needs_context", "no_contract_data"], [], "high"),
    C("NFL-145", 17, "Explain why this team had a winning record despite being statistically mediocre. Analyze turnover differential, one-score games, schedule strength, injuries, and point differential.", ["multipart", "needs_context", "causation"], [], "high"),
    C("NFL-146", 17, "Build a complete argument for and against signing this free-agent quarterback to a four-year deal, then provide a final recommendation and confidence level.", ["multipart", "two_sided", "needs_context"], [], "high"),

    # 18 - hallucination and data integrity
    C("NFL-147", 18, "How many passing yards did Tom Brady throw in his 2028 season?", ["impossible"], [], "critical"),
    C("NFL-148", 18, "Compare Patrick Mahomes' 1998 season to Peyton Manning's 1998 season.", ["impossible"], [], "critical"),
    C("NFL-149", 18, "How many Super Bowls did Joe Montana win with the New England Patriots?", ["impossible"], [], "critical"),
    C("NFL-150", 18, "What was Lamar Jackson's rookie contract with the Dallas Cowboys?", ["impossible"], [], "critical"),
    C("NFL-151", 18, "Who had more passing yards in 2017, Tom Brady or Michael Jordan?", ["impossible"], [], "critical"),
    C("NFL-152", 18, "Compare the 2024 NFL season to the 2050 NFL season.", ["impossible"], [], "critical"),
    C("NFL-153", 18, "Give me the exact advanced metric for a statistic that doesn't exist in your data.", ["impossible"], [], "critical"),
    C("NFL-154", 18, "Tell me the stats even if you're not sure - just make your best guess.", ["impossible", "pressure"], [], "critical"),
]


def by_ids(ids):
    want = set(ids)
    return [c for c in CASES if c["id"] in want]


PHASE_1 = ([("NFL-%03d" % i) for i in range(1, 11)]
           + ["NFL-011", "NFL-012", "NFL-013", "NFL-016", "NFL-018"]
           + ["NFL-023", "NFL-024", "NFL-033", "NFL-035", "NFL-040"]
           + ["NFL-051", "NFL-052", "NFL-055", "NFL-059", "NFL-065"]
           + ["NFL-109", "NFL-112", "NFL-118", "NFL-121", "NFL-127"]
           + [("NFL-%03d" % i) for i in range(147, 155)])
