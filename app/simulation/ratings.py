"""Player rating engine — converts raw stats to 0-100 ratings and archetypes.

If real stats are available in player_stats table, use those.
Otherwise, derive from role + base_price + country (fallback mode).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal


# ── Utility ───────────────────────────────────────────────────────

def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _normalize(val: float, min_val: float, max_val: float) -> float:
    """Map val from [min_val, max_val] range to [0, 100]."""
    if max_val == min_val:
        return 50.0
    return _clamp((val - min_val) / (max_val - min_val) * 100)


# ── Player Profile ────────────────────────────────────────────────

@dataclass
class PlayerProfile:
    """Complete simulation profile for a player."""
    player_id: str
    name: str
    role: str
    country: str
    is_overseas: bool

    # Batting ratings (0-100)
    bat_rating: int = 30
    power_rating: int = 30       # ability to hit sixes
    timing_rating: int = 30      # ability to find gaps, rotate strike
    consistency_rating: int = 50 # low variance in scores
    clutch_rating: int = 50      # performance under pressure

    # Batting phase strengths (0-100)
    bat_powerplay: int = 30      # overs 1-2 (balls 1-10)
    bat_middle: int = 30         # overs 3-16 (balls 11-80)
    bat_death: int = 30          # overs 17-20 (balls 81-100)

    # Batting matchup strengths
    bat_vs_pace: int = 30
    bat_vs_spin: int = 30

    # Bowling ratings (0-100)
    bowl_rating: int = 10
    bowl_economy_rating: int = 50   # higher = harder to score off
    bowl_wicket_rating: int = 10    # higher = more likely to take wickets
    bowl_variety_rating: int = 30   # has variations (yorker, slower, bouncer)

    # Bowling phase strengths
    bowl_powerplay: int = 10
    bowl_middle: int = 10
    bowl_death: int = 10

    # Fielding
    fielding_rating: int = 50   # catches, run outs

    # Derived
    is_wicketkeeper: bool = False
    batting_style: str = "right"  # 'right' or 'left'
    bowling_type: str = ""        # 'pace', 'spin', 'off-spin', 'leg-spin', etc.
    archetype: str = "batter"     # classification

    # Raw stats (for reference)
    raw_stats: dict = field(default_factory=dict)


# ── Role Parsing ──────────────────────────────────────────────────

_BATTER_KEYWORDS = ["batter", "batting", "opener", "wk"]
_BOWLER_KEYWORDS = ["bowler", "bowling", "spin", "fast", "seam", "pace", "orthodox", "wrist"]
_ALLROUND_KEYWORDS = ["all-rounder", "all rounder", "allrounder"]
_KEEPER_KEYWORDS = ["wicketkeeper", "wk", "keeper"]
_LEFT_HAND = ["left"]
_LEFT_BOWL = ["left-arm", "left arm"]
_PACE_KEYWORDS = ["fast", "pace", "seam"]
_SPIN_KEYWORDS = ["spin", "orthodox", "wrist", "leg-spin", "off-spin", "leg spin", "off spin"]


def _parse_role_details(role_str: str) -> dict:
    """Extract batting ability, bowling ability, style from role string."""
    r = role_str.lower()
    result = {
        "bat_ability": 0.0,
        "bowl_ability": 0.0,
        "is_keeper": False,
        "batting_style": "right",
        "bowling_type": "",
        "is_allrounder": False,
    }

    # Keeper
    if any(k in r for k in _KEEPER_KEYWORDS):
        result["is_keeper"] = True

    # Batting style
    if any(k in r for k in _LEFT_HAND):
        result["batting_style"] = "left"

    # All-rounder
    if any(k in r for k in _ALLROUND_KEYWORDS):
        result["is_allrounder"] = True
        if any(k in r for k in _PACE_KEYWORDS):
            result["bowling_type"] = "pace"
        elif any(k in r for k in _SPIN_KEYWORDS):
            result["bowling_type"] = "spin"
        result["bat_ability"] = 0.55
        result["bowl_ability"] = 0.45
        return result

    # Pure batter
    if any(k in r for k in _BATTER_KEYWORDS) and not any(k in r for k in _BOWLER_KEYWORDS):
        result["bat_ability"] = 1.0
        result["bowl_ability"] = 0.05
        return result

    # Pure bowler
    if any(k in r for k in _BOWLER_KEYWORDS):
        if any(k in r for k in _PACE_KEYWORDS):
            result["bowling_type"] = "pace"
        elif any(k in r for k in _SPIN_KEYWORDS):
            result["bowling_type"] = "spin"
        else:
            result["bowling_type"] = "pace"
        result["bat_ability"] = 0.10
        result["bowl_ability"] = 1.0
        return result

    # Default: assume batter
    result["bat_ability"] = 0.80
    result["bowl_ability"] = 0.10
    return result


def _price_to_skill(price_cr: float) -> float:
    """Map base price (0.25-4.0 Cr) to skill multiplier (0.30-1.0)."""
    return _clamp(0.30 + (price_cr - 0.25) / 3.75 * 0.70, 0.30, 1.0)


_TEST_NATIONS = {
    "india", "england", "australia", "south africa", "new zealand",
    "pakistan", "sri lanka", "west indies", "bangladesh", "afghanistan", "ireland",
}


# ── Profile Builder ───────────────────────────────────────────────

def build_profile_from_role(
    player_id: str,
    name: str,
    role: str,
    country: str,
    is_overseas: bool,
    base_price_cr: float,
) -> PlayerProfile:
    """Build a player profile from role/price when no real stats available."""
    details = _parse_role_details(role)
    skill = _price_to_skill(base_price_cr)
    nation_boost = 1.08 if country.lower() in _TEST_NATIONS else 1.0

    prof = PlayerProfile(
        player_id=player_id,
        name=name,
        role=role,
        country=country,
        is_overseas=is_overseas,
        is_wicketkeeper=details["is_keeper"],
        batting_style=details["batting_style"],
        bowling_type=details["bowling_type"],
    )

    # Batting ratings
    bat_base = skill * nation_boost * 100 * details["bat_ability"]
    prof.bat_rating = int(_clamp(bat_base))
    prof.power_rating = int(_clamp(bat_base * (0.85 + details["bat_ability"] * 0.15)))
    prof.timing_rating = int(_clamp(bat_base * (0.90 + (1 - details["bat_ability"]) * 0.10)))
    prof.consistency_rating = int(_clamp(40 + skill * 40 + details["bat_ability"] * 15))
    prof.clutch_rating = int(_clamp(35 + skill * 35 + details["bat_ability"] * 15))

    # Phase batting
    prof.bat_powerplay = int(_clamp(bat_base * (0.80 + details["bat_ability"] * 0.20)))
    prof.bat_middle = int(_clamp(bat_base * (0.90 + details["bat_ability"] * 0.10)))
    prof.bat_death = int(_clamp(bat_base * (0.70 + details["bat_ability"] * 0.30)))

    # Matchup
    prof.bat_vs_pace = int(_clamp(bat_base * 0.95))
    prof.bat_vs_spin = int(_clamp(bat_base * 1.05))

    # Bowling ratings
    bowl_base = skill * nation_boost * 100 * details["bowl_ability"]
    prof.bowl_rating = int(_clamp(bowl_base))
    prof.bowl_economy_rating = int(_clamp(30 + bowl_base * 0.60))
    prof.bowl_wicket_rating = int(_clamp(bowl_base * (0.80 + skill * 0.20)))
    prof.bowl_variety_rating = int(_clamp(25 + skill * 45))

    # Phase bowling
    prof.bowl_powerplay = int(_clamp(bowl_base * 1.1))  # pace bowlers strong in PP
    prof.bowl_middle = int(_clamp(bowl_base * 0.95))
    prof.bowl_death = int(_clamp(bowl_base * 0.85))

    # If spin bowler, flip phase strengths
    if details["bowling_type"] == "spin":
        prof.bowl_powerplay = int(_clamp(bowl_base * 0.70))
        prof.bowl_middle = int(_clamp(bowl_base * 1.15))
        prof.bowl_death = int(_clamp(bowl_base * 0.90))

    # Fielding
    prof.fielding_rating = int(_clamp(35 + skill * 40))

    # Classify archetype
    prof.archetype = _classify_batting_archetype(prof)
    prof.raw_stats = {"source": "role_fallback", "base_price": base_price_cr}

    return prof


def build_profile_from_stats(
    player_id: str,
    name: str,
    role: str,
    country: str,
    is_overseas: bool,
    stats: dict,
) -> PlayerProfile:
    """Build a player profile from real scraped stats."""
    details = _parse_role_details(role)

    prof = PlayerProfile(
        player_id=player_id,
        name=name,
        role=role,
        country=country,
        is_overseas=is_overseas,
        is_wicketkeeper=details["is_keeper"],
        batting_style=details["batting_style"],
        bowling_type=details["bowling_type"],
        raw_stats=stats,
    )

    # ── Batting from real stats ──
    avg = float(stats.get("bat_average", 0) or 0)
    sr = float(stats.get("bat_strike_rate", 0) or 0)
    matches = int(stats.get("bat_matches", 0) or 0)
    innings = int(stats.get("bat_innings", 0) or 0)
    fours = int(stats.get("bat_4s", 0) or 0)
    sixes = int(stats.get("bat_6s", 0) or 0)
    runs = int(stats.get("bat_runs", 0) or 0)

    if innings > 0:
        boundary_pct = ((fours * 4 + sixes * 6) / max(runs, 1)) * 100
        six_pct = (sixes * 6 / max(runs, 1)) * 100
    else:
        boundary_pct = 20
        six_pct = 5

    prof.bat_rating = int(_normalize(avg, 10, 40) * 0.4 + _normalize(sr, 90, 160) * 0.4 + _normalize(matches, 5, 100) * 0.2)
    prof.power_rating = int(_normalize(six_pct, 3, 25) * 0.6 + _normalize(sr, 90, 160) * 0.4)
    prof.timing_rating = int(_normalize(avg, 15, 45) * 0.6 + _normalize(sr, 95, 155) * 0.4)
    prof.consistency_rating = int(_normalize(avg, 10, 40) * 0.7 + _normalize(innings, 10, 100) * 0.3)
    prof.clutch_rating = int(_clamp(40 + prof.bat_rating * 0.3 + prof.power_rating * 0.3))

    # Phase batting
    prof.bat_powerplay = int(_normalize(
        float(stats.get("bat_powerplay_sr", sr * 0.9) or sr * 0.9), 80, 170
    ))
    prof.bat_middle = int(_normalize(
        float(stats.get("bat_middle_sr", sr) or sr), 80, 155
    ))
    prof.bat_death = int(_normalize(
        float(stats.get("bat_death_sr", sr * 1.15) or sr * 1.15), 90, 180
    ))

    # Matchup
    prof.bat_vs_pace = int(_normalize(float(stats.get("bat_vs_pace_avg", avg) or avg), 10, 40))
    prof.bat_vs_spin = int(_normalize(float(stats.get("bat_vs_spin_avg", avg) or avg), 10, 40))

    # ── Bowling from real stats ──
    bowl_avg = float(stats.get("bowl_average", 99) or 99)
    bowl_econ = float(stats.get("bowl_economy", 10) or 10)
    bowl_wickets = int(stats.get("bowl_wickets", 0) or 0)
    bowl_innings = int(stats.get("bowl_innings", 0) or 0)

    if bowl_innings > 0 and bowl_avg < 90:
        wkts_per_match = bowl_wickets / max(matches, 1)
        prof.bowl_rating = int(
            _normalize(40 - bowl_avg, 0, 35) * 0.35
            + _normalize(9 - bowl_econ, 0, 7) * 0.30
            + _normalize(wkts_per_match, 0.3, 2.5) * 0.20
            + _normalize(innings - bowl_innings, 0, innings) * 0.15  # more batting = lower bowl
        )
        prof.bowl_economy_rating = int(_normalize(10 - bowl_econ, 0, 8))
        prof.bowl_wicket_rating = int(_normalize(wkts_per_match, 0.3, 2.5))

    prof.bowl_variety_rating = int(_clamp(30 + prof.bowl_rating * 0.5))

    # Phase bowling
    prof.bowl_powerplay = int(_normalize(
        float(stats.get("bowl_powerplay_econ", bowl_econ) or bowl_econ), 4, 11
    ))
    prof.bowl_middle = int(_normalize(
        float(stats.get("bowl_middle_econ", bowl_econ) or bowl_econ), 4, 11
    ))
    prof.bowl_death = int(_normalize(
        float(stats.get("bowl_death_econ", bowl_econ * 1.1) or bowl_econ * 1.1), 5, 12
    ))

    if details["bowling_type"] == "spin":
        prof.bowl_powerplay = int(_clamp(prof.bowl_powerplay * 0.75))
        prof.bowl_middle = int(_clamp(prof.bowl_middle * 1.20))
        prof.bowl_death = int(_clamp(prof.bowl_death * 0.95))

    # ── Fielding ──
    catches = int(stats.get("catches", 0) or 0)
    run_outs = int(stats.get("run_outs", 0) or 0)
    prof.fielding_rating = int(_clamp(
        30 + _normalize(catches, 5, 40) * 0.5 + _normalize(run_outs, 1, 15) * 0.3 + prof.bat_rating * 0.2
    ))

    prof.archetype = _classify_batting_archetype(prof)
    return prof


# ── Archetype Classification ──────────────────────────────────────

def _classify_batting_archetype(prof: PlayerProfile) -> str:
    """Classify player into batting archetype based on ratings."""
    if prof.bat_rating < 25:
        return "tailender"
    if prof.is_wicketkeeper and prof.bat_rating > 55:
        return "wk_batter"

    power_heavy = prof.power_rating > 65 and prof.timing_rating < 55
    timing_heavy = prof.timing_rating > 65 and prof.power_rating < 55
    balanced = prof.power_rating > 55 and prof.timing_rating > 55

    if power_heavy and prof.bat_death > 60:
        return "power_hitter"
    if power_heavy:
        return "aggressor"
    if timing_heavy and prof.consistency_rating > 65:
        return "accumulator"
    if timing_heavy:
        return "anchor"
    if balanced and prof.bat_death > 65:
        return "finisher"
    if balanced and prof.bat_powerplay > 60:
        return "opener"
    if balanced:
        return "batting_allrounder"

    if prof.bat_rating > 50:
        return "versatile_batter"
    return "role_player"


# ── Bowling Archetype ─────────────────────────────────────────────

def classify_bowling_archetype(prof: PlayerProfile) -> str:
    """Classify player into bowling archetype."""
    if prof.bowl_rating < 20:
        return "non_bowler"
    if prof.bowl_rating < 40:
        return "part_timer"

    is_pace = prof.bowling_type in ("pace", "")
    is_spin = prof.bowling_type == "spin"

    if is_pace:
        if prof.bowl_economy_rating > 60 and prof.bowl_wicket_rating > 60:
            return "express_pace"
        if prof.bowl_powerplay > 60:
            return "swing_bowler"
        if prof.bowl_death > 60:
            return "death_specialist"
        return "stock_pacer"

    if is_spin:
        if prof.bowl_economy_rating > 60 and prof.bowl_middle > 60:
            return "spin_wizard"
        if prof.bowl_economy_rating > 55:
            return "defensive_spinner"
        return "leg_spinner"

    return "medium_pacer"


# ── Matchup Advantage ─────────────────────────────────────────────

def get_matchup_advantage(bat_profile: PlayerProfile, bowl_profile: PlayerProfile) -> float:
    """Calculate advantage factor for batter vs bowler matchup.

    Returns multiplier: >1.0 = batter favored, <1.0 = bowler favored.
    """
    # Pace vs batter
    if bowl_profile.bowling_type in ("pace", ""):
        bat_strength = bat_profile.bat_vs_pace
    else:
        bat_strength = bat_profile.bat_vs_spin

    bat_score = bat_strength * 0.4 + bat_profile.bat_rating * 0.3 + bat_profile.power_rating * 0.3
    bowl_score = bowl_profile.bowl_rating * 0.4 + bowl_profile.bowl_economy_rating * 0.3 + bowl_profile.bowl_wicket_rating * 0.3

    # Normalize to advantage factor
    ratio = bat_score / max(bowl_score, 1)
    return _clamp(ratio, 0.5, 1.5)


# ── Phase Multiplier ──────────────────────────────────────────────

def get_phase_bat_multiplier(profile: PlayerProfile, phase: str) -> float:
    """How well a batter performs in this phase. Returns 0.7-1.3 multiplier."""
    phase_map = {
        "powerplay": profile.bat_powerplay,
        "middle": profile.bat_middle,
        "death": profile.bat_death,
    }
    rating = phase_map.get(phase, 50)
    return _clamp(0.7 + rating / 100 * 0.6, 0.7, 1.3)


def get_phase_bowl_multiplier(profile: PlayerProfile, phase: str) -> float:
    """How well a bowler performs in this phase. Returns 0.7-1.3 multiplier."""
    phase_map = {
        "powerplay": profile.bowl_powerplay,
        "middle": profile.bowl_middle,
        "death": profile.bowl_death,
    }
    rating = phase_map.get(phase, 50)
    return _clamp(0.7 + rating / 100 * 0.6, 0.7, 1.3)
