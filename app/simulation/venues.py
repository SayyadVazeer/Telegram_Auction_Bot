"""12 English venue profiles with simulation modifiers.

Each venue has:
- batting_factor: >1.0 means easier batting (more boundaries)
- bowling_factor: >1.0 means easier bowling (more wickets)
- spin_factor: >1.0 means spinners more effective
- avg_first_innings: typical first innings score in The Hundred format
- boundary_rate: % of balls that result in 4 or 6
- wicket_rate: % of balls that result in a wicket
- pace_profile: how pace bowlers perform ('excellent', 'good', 'average', 'poor')
- spin_profile: how spinners perform ('excellent', 'good', 'average', 'poor')
- description: flavor text for commentary
"""

VENUES: dict[str, dict] = {
    "WT": {
        "name": "County Ground, Bristol",
        "batting_factor": 1.25,
        "bowling_factor": 0.80,
        "spin_factor": 0.85,
        "avg_first_innings": 165,
        "boundary_rate": 0.22,
        "wicket_rate": 0.06,
        "pace_profile": "poor",
        "spin_profile": "average",
        "description": (
            "A smaller, intimate ground with generally short boundaries all around. "
            "The pitch is usually very flat and devoid of grass in white-ball cricket. "
            "Extremely favorable for batting — edges often fly for six. "
            "Batters trust the bounce and hit through the line from ball one."
        ),
    },
    "LMI": {
        "name": "Lord's, London",
        "batting_factor": 0.95,
        "bowling_factor": 1.15,
        "spin_factor": 0.90,
        "avg_first_innings": 150,
        "boundary_rate": 0.16,
        "wicket_rate": 0.09,
        "pace_profile": "excellent",
        "spin_profile": "average",
        "description": (
            "The Home of Cricket, defined by its famous slope (drops 2.5m N-S). "
            "The slope assists seam movement significantly. Pavilion End drifts in, "
            "Nursery End shapes away. Wobble-seam is very effective here. "
            "A generally good batting deck, but rarely an absolute road."
        ),
    },
    "WF": {
        "name": "Sophia Gardens, Cardiff",
        "batting_factor": 0.90,
        "bowling_factor": 1.05,
        "spin_factor": 1.15,
        "avg_first_innings": 148,
        "boundary_rate": 0.15,
        "wicket_rate": 0.08,
        "pace_profile": "good",
        "spin_profile": "excellent",
        "description": (
            "Long square boundaries but very short straight boundaries. "
            "The pitch can be 'sticky' or two-paced. Cutters and slower balls "
            "grip into the surface effectively. Spinners enjoy bowling here — "
            "inconsistent bounce and turn make scoring difficult."
        ),
    },
    "SB": {
        "name": "Rose Bowl, Southampton",
        "batting_factor": 0.85,
        "bowling_factor": 1.10,
        "spin_factor": 1.20,
        "avg_first_innings": 142,
        "boundary_rate": 0.14,
        "wicket_rate": 0.08,
        "pace_profile": "good",
        "spin_profile": "excellent",
        "description": (
            "A large amphitheater with very long boundaries — some of the biggest in the UK. "
            "Batters must work hard for runs. Running between wickets is critical. "
            "Very spin-friendly — large boundaries allow spinners to flight the ball. "
            "Short-pitched bowling works well as batters hole out trying to clear the ropes."
        ),
    },
    "MSG": {
        "name": "Old Trafford, Manchester",
        "batting_factor": 1.05,
        "bowling_factor": 1.10,
        "spin_factor": 1.15,
        "avg_first_innings": 158,
        "boundary_rate": 0.18,
        "wicket_rate": 0.08,
        "pace_profile": "excellent",
        "spin_profile": "excellent",
        "description": (
            "England's fastest pitch with steep bounce. Large ground with expansive boundaries. "
            "The wicket is hard and abrasive. A paradise for back-foot players — "
            "true bounce allows confident pulling and cutting. "
            "Historically aids spinners; the abrasive surface allows the ball to grip."
        ),
    },
    "DD": {
        "name": "Riverside Ground, Chester-le-Street",
        "batting_factor": 0.95,
        "bowling_factor": 1.05,
        "spin_factor": 0.85,
        "avg_first_innings": 150,
        "boundary_rate": 0.16,
        "wicket_rate": 0.08,
        "pace_profile": "good",
        "spin_profile": "average",
        "description": (
            "An open ground that can be breezy with longer boundaries. "
            "The pitch retains moisture longer than southern grounds. "
            "Swing is often available even at 4 PM. Seamers who pitch it up get rewards. "
            "A fair contest between bat and ball."
        ),
    },
    "BP": {
        "name": "Edgbaston, Birmingham",
        "batting_factor": 1.05,
        "bowling_factor": 0.95,
        "spin_factor": 1.05,
        "avg_first_innings": 155,
        "boundary_rate": 0.18,
        "wicket_rate": 0.07,
        "pace_profile": "good",
        "spin_profile": "good",
        "description": (
            "Known for its electric atmosphere. Generally flat wicket with good carry. "
            "Hard and true surface allows batters to hit through the line early. "
            "The ball comes onto the bat nicely. Cross-seam deliveries and "
            "slower bouncers are key for pace bowlers."
        ),
    },
    "TR": {
        "name": "Trent Bridge, Nottingham",
        "batting_factor": 1.30,
        "bowling_factor": 0.75,
        "spin_factor": 0.80,
        "avg_first_innings": 172,
        "boundary_rate": 0.24,
        "wicket_rate": 0.05,
        "pace_profile": "poor",
        "spin_profile": "poor",
        "description": (
            "An absolute road. Short square boundaries on one side. "
            "World-renowned for white-ball records. No total is truly safe here. "
            "Batters target the short boundary relentlessly. "
            "A graveyard for errant fast bowling — wide yorkers are the standard play."
        ),
    },
    "SRL": {
        "name": "Headingley, Leeds",
        "batting_factor": 1.20,
        "bowling_factor": 0.82,
        "spin_factor": 0.85,
        "avg_first_innings": 162,
        "boundary_rate": 0.21,
        "wicket_rate": 0.06,
        "pace_profile": "average",
        "spin_profile": "average",
        "description": (
            "A compact ground and one of the highest-scoring in the country. "
            "The ball skids on beautifully with a lightning-fast outfield. "
            "The wicket stays true for the full duration. "
            "Swing is minimal unless there is cloud cover."
        ),
    },
    "OI": {
        "name": "The Oval, Kennington, London",
        "batting_factor": 1.15,
        "bowling_factor": 0.90,
        "spin_factor": 1.05,
        "avg_first_innings": 160,
        "boundary_rate": 0.19,
        "wicket_rate": 0.07,
        "pace_profile": "good",
        "spin_profile": "good",
        "description": (
            "A large, expansive ground with a very flat, hard surface. "
            "Known for true bounce and consistent pace. "
            "Traditionally the best batting wicket in England — high scores are the norm. "
            "The pitch can be dry, offering purchase for spinners later in summer."
        ),
    },
    "SM": {
        "name": "County Ground, Taunton",
        "batting_factor": 1.35,
        "bowling_factor": 0.72,
        "spin_factor": 0.80,
        "avg_first_innings": 175,
        "boundary_rate": 0.25,
        "wicket_rate": 0.05,
        "pace_profile": "poor",
        "spin_profile": "average",
        "description": (
            "Famously small boundaries all around with a lightning-fast outfield. "
            "A batting paradise — even late in summer the pitch remains extremely firm. "
            "Batters trust the bounce and hit cleanly through the line. "
            "Pace bowlers must bowl defensive lines — wide yorkers and slower balls."
        ),
    },
    "DF": {
        "name": "County Ground, Derby",
        "batting_factor": 0.88,
        "bowling_factor": 1.12,
        "spin_factor": 1.25,
        "avg_first_innings": 145,
        "boundary_rate": 0.14,
        "wicket_rate": 0.09,
        "pace_profile": "good",
        "spin_profile": "excellent",
        "description": (
            "A large, expansive outfield with significantly longer boundaries. "
            "Traditionally a slightly slower, lower-bouncing surface. "
            "Batting requires calculated approach — piercing gaps and aggressive running. "
            "Excellent conditions for spinners with reliable turn and hold."
        ),
    },
}

# Venue short codes for display
VENUE_LIST = [
    ("WT", "County Ground, Bristol"),
    ("LMI", "Lord's, London"),
    ("WF", "Sophia Gardens, Cardiff"),
    ("SB", "Rose Bowl, Southampton"),
    ("MSG", "Old Trafford, Manchester"),
    ("DD", "Riverside Ground, Chester-le-Street"),
    ("BP", "Edgbaston, Birmingham"),
    ("TR", "Trent Bridge, Nottingham"),
    ("SRL", "Headingley, Leeds"),
    ("OI", "The Oval, Kennington, London"),
    ("SM", "County Ground, Taunton"),
    ("DF", "County Ground, Derby"),
]


def get_venue(code: str) -> dict:
    """Get venue profile by short code."""
    return VENUES.get(code, VENUES["BP"])  # default to Edgbaston
