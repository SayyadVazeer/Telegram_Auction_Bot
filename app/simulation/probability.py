"""Ball outcome probability model.

For each delivery, calculates weighted probabilities for all possible outcomes
based on batter profile, bowler profile, venue, phase, and match situation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from app.simulation.ratings import (
    PlayerProfile,
    _clamp,
    get_matchup_advantage,
    get_phase_bat_multiplier,
    get_phase_bowl_multiplier,
)


# ── Outcome Types ─────────────────────────────────────────────────

OUTCOMES = [
    "dot",        # 0 runs
    "single",     # 1 run
    "double",     # 2 runs
    "triple",     # 3 runs (rare)
    "four",       # boundary 4
    "six",        # boundary 6
    "wicket",     # any dismissal
    "wide",       # wide delivery + 1 run
    "noball",     # no ball + 1 run + free hit
    "bye",        # bye run(s)
    "legbye",     # leg bye run(s)
]

# Dismissal sub-types (selected if outcome == "wicket")
DISMISSAL_TYPES = [
    "bowled",
    "caught",
    "lbw",
    "caught_behind",
    "caught_bowled",
    "run_out",
    "stumped",
    "hit_wicket",
]

# Delivery descriptions for commentary variety
PACE_DELIVERIES = [
    "good length", "short of a length", "full and straight",
    "yorker", "short ball", "bouncer", "wide of off stump",
    "slower ball", "back of a hand slower", "cross-seam",
    "inswinger", "outswinger", "off cutter", "leg cutter",
    "short of a good length", "full outside off", "on the pads",
]

SPIN_DELIVERIES = [
    "flighted delivery", "flat and fast", "tossed up",
    "arm ball", "googly", "doosra", "slider",
    "outside off", "on middle stump", "short of a length",
    "quicker through the air", "dip and turn", "wide of off",
]

REGIONS = [
    "through covers", "over mid-off", "straight back past the bowler",
    "through midwicket", "over long-on", "over deep midwicket",
    "fine leg", "third man", "square leg", "point",
    "backward square leg", "deep square leg", "long leg",
    "over long-off", "over extra cover", "through extra cover",
    "behind square", "swept fine", "over cow corner",
    "down the ground", "over midwicket", "through point",
    "past short third man", "behind point",
]

WICKET_REGIONS = [
    "at deep midwicket", "at long-on", "at deep cover",
    "at short fine leg", "at deep square leg", "at mid-off",
    "at mid-on", "at point", "at backward point",
    "at slip", "at gully", "at short leg",
    "at silly point", "at leg slip",
]

FREE_HIT_OUTCOMES = ["single", "double", "four", "six", "bye", "legbye", "dot"]


# ── Ball Outcome ──────────────────────────────────────────────────

@dataclass
class BallOutcome:
    """Result of a single delivery."""
    outcome: str              # main outcome type
    runs_scored: int = 0      # runs off the bat
    extras: int = 0           # extras (wide, no-ball, bye, legbye)
    total_runs: int = 0       # total runs on this ball
    is_wicket: bool = False
    dismissal_type: str = ""
    dismissal_detail: str = ""  # "caught at deep midwicket"
    fielder_name: str = ""
    delivery_type: str = ""   # "good length", "yorker", etc.
    region: str = ""          # "through covers", etc.
    is_free_hit: bool = False


# ── Probability Calculator ────────────────────────────────────────

def calculate_probabilities(
    bat: PlayerProfile,
    bowl: PlayerProfile,
    venue: dict,
    phase: str,               # "powerplay", "middle", "death"
    balls_remaining: int,     # out of 100
    partnership_balls: int,   # current partnership balls faced
    partnership_runs: int,    # current partnership runs
    runs_needed: Optional[int] = None,  # 2nd innings chase
    total_wickets_fallen: int = 0,
    is_free_hit: bool = False,
) -> dict[str, float]:
    """Calculate ball outcome probabilities.

    Returns dict mapping outcome name to probability (0-1).
    """
    # ── Base probabilities ──
    probs = {
        "dot": 28.0,
        "single": 24.0,
        "double": 9.0,
        "triple": 1.5,
        "four": 11.0,
        "six": 6.0,
        "wicket": 8.0,
        "wide": 3.5,
        "noball": 2.0,
        "bye": 1.5,
        "legbye": 1.5,
    }

    # ── Batter skill modifier ──
    bat_mod = (bat.bat_rating - 50) / 100  # -0.5 to +0.5
    probs["dot"] -= bat_mod * 10
    probs["single"] += bat_mod * 3
    probs["four"] += bat_mod * 6
    probs["six"] += bat_mod * 4
    probs["wicket"] -= bat_mod * 4

    # Power rating → more sixes, more dots
    power_mod = (bat.power_rating - 50) / 100
    probs["six"] += power_mod * 8
    probs["four"] += power_mod * 3
    probs["dot"] += power_mod * 2  # power hitters miss more

    # Timing rating → more singles/doubles, fewer dots
    timing_mod = (bat.timing_rating - 50) / 100
    probs["single"] += timing_mod * 5
    probs["double"] += timing_mod * 3
    probs["dot"] -= timing_mod * 6

    # Consistency → fewer wickets
    cons_mod = (bat.consistency_rating - 50) / 100
    probs["wicket"] -= cons_mod * 3

    # ── Bowler skill modifier ──
    bowl_mod = (bowl.bowl_rating - 50) / 100
    probs["wicket"] += bowl_mod * 5
    probs["dot"] += bowl_mod * 4
    probs["four"] -= bowl_mod * 3
    probs["six"] -= bowl_mod * 2
    probs["single"] -= bowl_mod * 2

    # Economy rating → fewer boundaries
    econ_mod = (bowl.bowl_economy_rating - 50) / 100
    probs["four"] -= econ_mod * 4
    probs["six"] -= econ_mod * 3
    probs["single"] += econ_mod * 2

    # Wicket rating → more wickets
    wk_mod = (bowl.bowl_wicket_rating - 50) / 100
    probs["wicket"] += wk_mod * 4

    # ── Matchup advantage ──
    advantage = get_matchup_advantage(bat, bowl)
    if advantage > 1.0:  # batter favored
        boost = (advantage - 1.0) * 8
        probs["four"] += boost
        probs["six"] += boost * 0.7
        probs["wicket"] -= boost * 0.5
        probs["dot"] -= boost * 0.3
    else:  # bowler favored
        boost = (1.0 - advantage) * 8
        probs["wicket"] += boost
        probs["dot"] += boost * 0.5
        probs["four"] -= boost * 0.3
        probs["six"] -= boost * 0.3

    # ── Phase modifiers ──
    bat_phase = get_phase_bat_multiplier(bat, phase)
    bowl_phase = get_phase_bowl_multiplier(bowl, phase)

    if phase == "powerplay":
        # Fielding restrictions → more boundaries
        probs["four"] *= 1.25
        probs["six"] *= 1.15
        probs["wicket"] *= 1.05  # batters take risks
        probs["single"] *= 0.95
    elif phase == "death":
        # Must attack → more boundaries, more wickets
        probs["six"] *= 1.45
        probs["four"] *= 1.20
        probs["wicket"] *= 1.20
        probs["dot"] *= 0.65
        probs["single"] *= 0.80
        probs["double"] *= 0.70
    else:  # middle
        probs["single"] *= 1.10
        probs["double"] *= 1.15

    # Apply phase multipliers
    for key in ["four", "six"]:
        probs[key] *= bat_phase
    for key in ["wicket", "dot"]:
        probs[key] *= bowl_phase

    # ── Archetype modifiers ──
    if bat.archetype == "power_hitter":
        probs["six"] *= 1.6
        probs["four"] *= 1.2
        probs["dot"] *= 1.3
        probs["wicket"] *= 1.15
    elif bat.archetype == "accumulator":
        probs["single"] *= 1.3
        probs["double"] *= 1.2
        probs["dot"] *= 0.75
        probs["wicket"] *= 0.80
        probs["six"] *= 0.6
    elif bat.archetype == "anchor":
        probs["single"] *= 1.4
        probs["dot"] *= 0.70
        probs["wicket"] *= 0.75
        probs["six"] *= 0.5
        probs["four"] *= 0.9
    elif bat.archetype == "finisher":
        probs["six"] *= 1.3
        probs["four"] *= 1.15
        probs["wicket"] *= 1.10
    elif bat.archetype == "tailender":
        probs["dot"] *= 1.6
        probs["wicket"] *= 1.8
        probs["six"] *= 0.25
        probs["four"] *= 0.4
        probs["single"] *= 0.8
    elif bat.archetype == "wk_batter":
        probs["four"] *= 1.1
        probs["single"] *= 1.1

    # Bowling archetype
    bowl_type = _classify_bowl_archetype(bowl)
    if bowl_type == "express_pace":
        probs["wicket"] *= 1.25
        probs["dot"] *= 1.15
    elif bowl_type == "death_specialist":
        if phase == "death":
            probs["six"] *= 0.70
            probs["four"] *= 0.80
            probs["wicket"] *= 1.15
    elif bowl_type == "spin_wizard":
        if phase == "middle":
            probs["dot"] *= 1.20
            probs["wicket"] *= 1.10
            probs["single"] *= 0.90
    elif bowl_type == "part_timer":
        probs["four"] *= 1.20
        probs["six"] *= 1.15
        probs["wicket"] *= 0.60
        probs["dot"] *= 0.80

    # ── Venue modifiers ──
    bf = venue.get("batting_factor", 1.0)
    wf = venue.get("bowling_factor", 1.0)
    sf = venue.get("spin_factor", 1.0)

    probs["four"] *= bf
    probs["six"] *= bf
    probs["wicket"] *= wf

    if bowl.bowling_type == "spin":
        probs["wicket"] *= sf
        probs["dot"] *= (1 + (sf - 1) * 0.5)

    # ── Match situation modifiers ──
    # Partnership building — longer partnership = more comfortable
    if partnership_balls > 15:
        comfort = min(partnership_balls / 40, 1.5)
        probs["wicket"] *= (1 - (comfort - 1) * 0.15) if comfort > 1 else 1.0
        probs["four"] *= (1 + (comfort - 1) * 0.10) if comfort > 1 else 1.0

    # Chase pressure (2nd innings)
    if runs_needed is not None and runs_needed > 0 and balls_remaining > 0:
        required_rate = runs_needed / balls_remaining
        if required_rate > 12:  # extreme pressure
            probs["six"] *= 1.4
            probs["four"] *= 1.2
            probs["wicket"] *= 1.3
            probs["dot"] *= 0.6
            probs["single"] *= 0.7
        elif required_rate > 8:  # moderate pressure
            probs["six"] *= 1.15
            probs["wicket"] *= 1.10
            probs["dot"] *= 0.85
        elif required_rate < 5:  # comfortable — bat carefully
            probs["dot"] *= 1.15
            probs["wicket"] *= 0.85
            probs["six"] *= 0.85

    # Early wickets → tail comes in → more wickets likely
    if total_wickets_fallen >= 6:
        probs["wicket"] *= 1.10
        probs["dot"] *= 1.05

    # ── Extras probability adjustments ──
    # Pace bowlers slightly more likely to bowl wides/no-balls
    if bowl.bowling_type in ("pace", ""):
        probs["wide"] *= 1.15
        probs["noball"] *= 1.10
    # Spin bowlers more likely to be swept → byes
    if bowl.bowling_type == "spin":
        probs["bye"] *= 1.3
        probs["legbye"] *= 1.2

    # ── Free hit modifier ──
    if is_free_hit:
        # Can't be bowled/LBW/stumped on a free hit
        probs["wicket"] *= 0.35  # only caught/run out/hit wicket possible
        probs["six"] *= 1.3
        probs["four"] *= 1.2
        probs["dot"] *= 0.7

    # ── Normalize ──
    return _normalize_probs(probs)


def _classify_bowl_archetype(bowl: PlayerProfile) -> str:
    """Quick bowling archetype classification."""
    if bowl.bowl_rating < 40:
        return "part_timer"
    if bowl.bowling_type in ("pace", ""):
        if bowl.bowl_economy_rating > 60 and bowl.bowl_wicket_rating > 60:
            return "express_pace"
        if bowl.bowl_death > 60:
            return "death_specialist"
        if bowl.bowl_powerplay > 60:
            return "swing_bowler"
        return "stock_pacer"
    if bowl.bowling_type == "spin":
        if bowl.bowl_economy_rating > 60 and bowl.bowl_middle > 60:
            return "spin_wizard"
        return "spinner"
    return "medium_pacer"


def _normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    """Ensure all probabilities are non-negative and sum to 1.0."""
    for k in probs:
        probs[k] = max(probs[k], 0.05)  # minimum 0.5% chance for everything

    total = sum(probs.values())
    if total == 0:
        # Fallback: equal probabilities
        n = len(probs)
        return {k: 1.0 / n for k in probs}
    return {k: v / total for k, v in probs.items()}


# ── Outcome Selection ─────────────────────────────────────────────

def select_outcome(probs: dict[str, float], is_free_hit: bool = False) -> BallOutcome:
    """Select a ball outcome using weighted random based on probabilities."""
    outcomes = list(probs.keys())
    weights = [probs[k] for k in outcomes]

    chosen = random.choices(outcomes, weights=weights, k=1)[0]

    # Build BallOutcome
    result = BallOutcome(outcome=chosen)
    result.delivery_type = random.choice(PACE_DELIVERIES)  # default

    if chosen == "dot":
        result.runs_scored = 0
        result.region = random.choice(["defended", "left alone", "played and missed"])
    elif chosen == "single":
        result.runs_scored = 1
        result.region = random.choice(REGIONS[:12])
    elif chosen == "double":
        result.runs_scored = 2
        result.region = random.choice(REGIONS[:15])
    elif chosen == "triple":
        result.runs_scored = 3
        result.region = random.choice(REGIONS[:10])
    elif chosen == "four":
        result.runs_scored = 4
        result.region = random.choice(REGIONS)
    elif chosen == "six":
        result.runs_scored = 6
        result.region = random.choice([
            "over long-on", "over deep midwicket", "over cow corner",
            "over long-off", "over deep cover", "down the ground",
            "over extra cover", "over midwicket",
        ])
    elif chosen == "wicket":
        result.is_wicket = True
        result.runs_scored = 0
        result.dismissal_type = _select_dismissal_type()
        result.region = random.choice(WICKET_REGIONS)
    elif chosen == "wide":
        result.extras = 1
        result.total_runs = 1
        return result
    elif chosen == "noball":
        result.extras = 1
        result.total_runs = 1
        result.is_free_hit = True
        return result
    elif chosen == "bye":
        result.extras = random.choices([1, 2], weights=[0.8, 0.2])[0]
        result.total_runs = result.extras
        return result
    elif chosen == "legbye":
        result.extras = random.choices([1, 2], weights=[0.85, 0.15])[0]
        result.total_runs = result.extras
        return result

    result.total_runs = result.runs_scored + result.extras
    return result


def _select_dismissal_type() -> str:
    """Select dismissal type with realistic weights."""
    types = [
        ("caught", 40),
        ("bowled", 20),
        ("lbw", 15),
        ("caught_behind", 10),
        ("caught_bowled", 3),
        ("run_out", 5),
        ("stumped", 4),
        ("hit_wicket", 3),
    ]
    names, weights = zip(*types)
    return random.choices(names, weights=weights, k=1)[0]


# ── Profile Cache ─────────────────────────────────────────────────

_profile_cache: dict[str, PlayerProfile] = {}


def get_cached_profile(player_id: str) -> Optional[PlayerProfile]:
    """Get a cached player profile."""
    return _profile_cache.get(player_id)


def set_cached_profile(profile: PlayerProfile) -> None:
    """Cache a player profile."""
    _profile_cache[profile.player_id] = profile


def clear_profile_cache() -> None:
    """Clear the profile cache."""
    _profile_cache.clear()
