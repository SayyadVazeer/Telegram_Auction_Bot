"""Core simulation engine — orchestrates the full match simulation.

Flow:
1. Toss → bat/bowl decision
2. Innings 1: 100 balls with owner bowling choices
3. Innings break: scorecard
4. Innings 2: 100 balls with owner bowling choices
5. Result + POTM + scorecards
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Callable, Optional, Awaitable

from app.simulation.match_state import (
    BALLS_PER_INNINGS,
    BALLS_PER_OVER,
    InningsState,
    MatchState,
)
from app.simulation.probability import (
    BallOutcome,
    calculate_probabilities,
    select_outcome,
)
from app.simulation.ratings import (
    PlayerProfile,
    build_profile_from_role,
    build_profile_from_stats,
    classify_bowling_archetype,
)
from app.simulation.probability import (
    get_cached_profile,
    set_cached_profile,
    clear_profile_cache,
)
from app.simulation.commentary import (
    generate_ball_commentary,
    generate_score_update,
    generate_innings_summary,
    generate_match_result,
    generate_venue_intro,
    generate_toss_result,
    generate_innings_start,
)
from app.simulation.venues import get_venue

logger = logging.getLogger(__name__)


# ── Profile Loader ────────────────────────────────────────────────

async def load_player_profile(player) -> PlayerProfile:
    """Load a player profile — from DB stats if available, else from role/price."""
    pid = player.player_id

    cached = get_cached_profile(pid)
    if cached:
        return cached

    # Try loading from player_stats table
    from app.simulation.stats_scraper import load_stats_from_db
    stats = await load_stats_from_db(pid)

    if stats and stats.get("bat_matches", 0) and stats.get("bat_matches", 0) > 0:
        profile = build_profile_from_stats(
            player_id=pid,
            name=player.name,
            role=player.role,
            country=player.country,
            is_overseas=player.is_overseas,
            stats=stats,
        )
    else:
        profile = build_profile_from_role(
            player_id=pid,
            name=player.name,
            role=player.role,
            country=player.country,
            is_overseas=player.is_overseas,
            base_price_cr=float(player.base_price_cr),
        )

    set_cached_profile(profile)
    return profile


# ── Match Simulation Callbacks ────────────────────────────────────

# Type for callback functions that send messages to Telegram
SendFunc = Callable[[str], Awaitable[None]]
SendPhotoFunc = Callable[[str, str], Awaitable[None]]
AskBowlerFunc = Callable[[int, list], Awaitable[str]]  # team_id, available_bowlers -> bowler_id
AskBatterFunc = Callable[[int, list], Awaitable[str]]  # team_id, available_batters -> batter_id


# ── Toss Simulation ───────────────────────────────────────────────

def simulate_toss(team1_name: str, team2_name: str) -> tuple[str, str]:
    """Simulate toss. Returns (winner_name, decision)."""
    winner = random.choice([team1_name, team2_name])
    # Decision based on venue
    decision = random.choice(["bat", "bowl"])
    return winner, decision


# ── Innings Simulation ────────────────────────────────────────────

async def simulate_innings(
    match_state: MatchState,
    match_id: int,
    innings_number: int,
    batting_team_id: int,
    bowling_team_id: int,
    batting_team_name: str,
    bowling_team_name: str,
    batting_order_ids: list[str],
    opener1_id: str,
    opener2_id: str,
    profiles: dict[str, PlayerProfile],
    players_map: dict[str, object],  # player_id -> Player model
    venue: dict,
    target: Optional[int] = None,
    send_message: Optional[SendFunc] = None,
    ask_bowler: Optional[AskBowlerFunc] = None,
    ask_batter: Optional[AskBatterFunc] = None,
    speed: str = "normal",  # "fast", "normal", "highlights"
) -> tuple[InningsState, list[dict]]:
    """Simulate one innings ball-by-ball.

    Returns (innings_state, list_of_ball_summaries).
    """
    # Get opener profiles
    opener1_profile = profiles.get(opener1_id)
    opener2_profile = profiles.get(opener2_id)

    # Determine first bowler (highest rated available)
    first_bowler_id = bowling_team_id  # placeholder, will be overridden
    first_bowler_name = "Bowler"

    # Start innings
    innings = match_state.start_innings(
        innings_number=innings_number,
        batting_team_id=batting_team_id,
        bowling_team_id=bowling_team_id,
        batting_team_name=batting_team_name,
        bowling_team_name=bowling_team_name,
        opening_batter1_id=opener1_id,
        opening_batter1_name=players_map.get(opener1_id, type("", (), {"name": "Unknown"})()).name if opener1_id in players_map else opener1_id,
        opening_batter2_id=opener2_id,
        opening_batter2_name=players_map.get(opener2_id, type("", (), {"name": "Unknown"})()).name if opener2_id in players_map else opener2_id,
        first_bowler_id=first_bowler_id,
        first_bowler_name=first_bowler_name,
        batting_order=batting_order_ids,
        target=target,
    )

    all_balls = []

    # Send innings start message
    if send_message:
        msg = generate_innings_start(innings_number, batting_team_name, bowling_team_name, target)
        await send_message(msg)
        await asyncio.sleep(2)

    # Simulate 100 balls
    for ball_num in range(1, BALLS_PER_INNINGS + 1):
        if innings.is_complete:
            break

        # Check if we need a new over (every 5 balls)
        if innings.balls_in_current_over == 0 and ball_num > 1:
            # Ask admin/owner for next bowler
            if ask_bowler:
                # Get available bowlers
                bowler_ids = _get_available_bowlers(innings, bowling_team_id, players_map)
                if bowler_ids:
                    new_bowler_id = await ask_bowler(bowling_team_id, bowler_ids)
                    if new_bowler_id and new_bowler_id in players_map:
                        bowler = players_map[new_bowler_id]
                        innings.set_next_bowler(new_bowler_id, bowler.name)

        # Get current profiles
        striker_profile = profiles.get(innings.striker_id)
        non_striker_profile = profiles.get(innings.non_striker_id)
        bowler_profile = profiles.get(innings.current_bowler_id)

        if not striker_profile or not bowler_profile:
            # Fallback: use basic profile
            if not striker_profile:
                striker_profile = PlayerProfile(
                    player_id=innings.striker_id, name=innings.striker_name,
                    role="Batter", country="", is_overseas=False,
                )
            if not bowler_profile:
                bowler_profile = PlayerProfile(
                    player_id=innings.current_bowler_id, name=innings.current_bowler_name,
                    role="Fast Bowler", country="", is_overseas=False,
                )

        # Calculate probabilities
        probs = calculate_probabilities(
            bat=striker_profile,
            bowl=bowler_profile,
            venue=venue,
            phase=innings.phase,
            balls_remaining=innings.balls_remaining,
            partnership_balls=innings.partnership.balls,
            partnership_runs=innings.partnership.runs,
            runs_needed=innings.runs_needed,
            total_wickets_fallen=innings.total_wickets,
            is_free_hit=innings.is_free_hit,
        )

        # Select outcome
        outcome = select_outcome(probs, is_free_hit=innings.is_free_hit)

        # Process ball
        summary = match_state.process_ball(outcome)
        summary["outcome"] = outcome

        # Generate commentary
        over_num = summary.get("over_number", 1)
        ball_in_over = summary.get("ball_in_over", 1)
        commentary_text = generate_ball_commentary(
            ball_num=ball_num,
            over_num=over_num,
            ball_in_over=ball_in_over,
            striker_name=innings.striker_name,
            bowler_name=innings.current_bowler_name,
            outcome=outcome,
            partnership_runs=innings.partnership.runs,
            partnership_balls=innings.partnership.balls,
        )
        summary["commentary"] = commentary_text
        all_balls.append(summary)

        # Handle wicket — ask for next batter
        if outcome.is_wicket and not innings.is_complete and ask_batter:
            available = _get_available_batters(innings, batting_order_ids, players_map)
            if available:
                new_batter_id = await ask_batter(batting_team_id, available)
                if new_batter_id and new_batter_id in players_map:
                    batter = players_map[new_batter_id]
                    innings.set_next_batter(new_batter_id, batter.name)
                    # Update profile
                    if new_batter_id not in profiles:
                        profiles[new_batter_id] = await load_player_profile(batter)

        # Send commentary based on speed mode
        if send_message:
            if speed == "fast":
                # Send every 5 balls (end of over)
                if ball_num % 5 == 0 or innings.is_complete:
                    await send_message(commentary_text)
                    await asyncio.sleep(0.5)
            elif speed == "highlights":
                # Send only wickets and boundaries
                if outcome.is_wicket or outcome.outcome in ("four", "six"):
                    await send_message(commentary_text)
                    await asyncio.sleep(0.5)
            else:  # normal
                await send_message(commentary_text)
                await asyncio.sleep(0.3)

            # Score update every 2 overs (10 balls)
            if ball_num % 10 == 0 and not innings.is_complete:
                score_msg = generate_score_update(innings, batting_team_name)
                await send_message(score_msg)
                await asyncio.sleep(1)

    # Innings complete
    return innings, all_balls


def _get_available_bowlers(
    innings: InningsState,
    bowling_team_id: int,
    players_map: dict,
) -> list[str]:
    """Get bowlers who haven't exceeded their max balls."""
    available = []
    for pid, stat in innings.bowling_stats.items():
        if stat.balls_bowled < 20:  # MAX_PER_BOWLER
            available.append(pid)
    # Also include bowlers not yet used
    for pid, player in players_map.items():
        if pid not in innings.bowling_stats:
            # Check if they're a bowler type
            profile = get_cached_profile(pid)
            if profile and profile.bowl_rating > 30:
                available.append(pid)
    return available


def _get_available_batters(
    innings: InningsState,
    batting_order: list[str],
    players_map: dict,
) -> list[str]:
    """Get batters who haven't batted yet (not in batting_stats)."""
    available = []
    for pid in batting_order:
        if pid not in innings.batting_stats:
            available.append(pid)
    return available


# ── Full Match Simulation ─────────────────────────────────────────

async def simulate_full_match(
    match_id: int,
    team1_id: int,
    team2_id: int,
    team1_name: str,
    team2_name: str,
    venue_code: str,
    team1_batting_order: list[str],
    team2_batting_order: list[str],
    team1_opener1: str,
    team1_opener2: str,
    team2_opener1: str,
    team2_opener2: str,
    profiles: dict[str, PlayerProfile],
    players_map: dict[str, object],
    toss_winner_id: int,
    toss_decision: str,
    send_message: Optional[SendFunc] = None,
    ask_bowler: Optional[AskBowlerFunc] = None,
    ask_batter: Optional[AskBatterFunc] = None,
    speed: str = "normal",
) -> dict:
    """Simulate a complete match (both innings).

    Returns match result dict.
    """
    venue = get_venue(venue_code)

    # Initialize match state
    match_state = MatchState(
        match_id=match_id,
        team1_id=team1_id,
        team2_id=team2_id,
        team1_name=team1_name,
        team2_name=team2_name,
        venue_code=venue_code,
    )
    match_state.toss_winner_id = toss_winner_id
    match_state.toss_decision = toss_decision

    # Determine batting order
    if toss_decision == "bat":
        first_batting_id = toss_winner_id
        first_batting_name = team1_name if toss_winner_id == team1_id else team2_name
        second_batting_id = team2_id if toss_winner_id == team1_id else team1_id
        second_batting_name = team2_name if toss_winner_id == team1_id else team1_name

        first_bat_order = team1_batting_order if toss_winner_id == team1_id else team2_batting_order
        second_bat_order = team2_batting_order if toss_winner_id == team1_id else team1_batting_order
        first_openers = (team1_opener1, team1_opener2) if toss_winner_id == team1_id else (team2_opener1, team2_opener2)
        second_openers = (team2_opener1, team2_opener2) if toss_winner_id == team1_id else (team1_opener1, team1_opener2)
    else:
        first_batting_id = team2_id if toss_winner_id == team1_id else team1_id
        first_batting_name = team2_name if toss_winner_id == team1_id else team1_name
        second_batting_id = team1_id if toss_winner_id == team1_id else team2_id
        second_batting_name = team1_name if toss_winner_id == team1_id else team2_name

        first_bat_order = team2_batting_order if toss_winner_id == team1_id else team1_batting_order
        second_bat_order = team1_batting_order if toss_winner_id == team1_id else team2_batting_order
        first_openers = (team2_opener1, team2_opener2) if toss_winner_id == team1_id else (team1_opener1, team1_opener2)
        second_openers = (team1_opener1, team1_opener2) if toss_winner_id == team1_id else (team2_opener1, team2_opener2)

    # Send toss result
    if send_message:
        toss_msg = generate_toss_result(
            team1_name if toss_winner_id == team1_id else team2_name,
            toss_decision,
            venue["name"],
        )
        await send_message(toss_msg)
        venue_msg = generate_venue_intro(venue)
        await send_message(venue_msg)
        await asyncio.sleep(3)

    # ── Innings 1 ──
    innings1, balls1 = await simulate_innings(
        match_state=match_state,
        match_id=match_id,
        innings_number=1,
        batting_team_id=first_batting_id,
        bowling_team_id=second_batting_id,
        batting_team_name=first_batting_name,
        bowling_team_name=second_batting_name,
        batting_order_ids=first_bat_order,
        opener1_id=first_openers[0],
        opener2_id=first_openers[1],
        profiles=profiles,
        players_map=players_map,
        venue=venue,
        send_message=send_message,
        ask_bowler=ask_bowler,
        ask_batter=ask_batter,
        speed=speed,
    )

    target = innings1.total_runs + 1

    # Innings break
    if send_message:
        summary_msg = generate_innings_summary(innings1, first_batting_name, target)
        await send_message(summary_msg)
        await asyncio.sleep(3)

    # ── Innings 2 ──
    innings2, balls2 = await simulate_innings(
        match_state=match_state,
        match_id=match_id,
        innings_number=2,
        batting_team_id=second_batting_id,
        bowling_team_id=first_batting_id,
        batting_team_name=second_batting_name,
        bowling_team_name=first_batting_name,
        batting_order_ids=second_bat_order,
        opener1_id=second_openers[0],
        opener2_id=second_openers[1],
        profiles=profiles,
        players_map=players_map,
        venue=venue,
        target=target,
        send_message=send_message,
        ask_bowler=ask_bowler,
        ask_batter=ask_batter,
        speed=speed,
    )

    # ── Determine Result ──
    result = _determine_result(match_state, innings1, innings2, target)

    # Send result
    if send_message:
        result_msg = generate_match_result(
            match_state=match_state,
            winning_team_name=result["winner_name"],
            losing_team_name=result["loser_name"],
            result_type=result["result_type"],
            result_detail=result["result_detail"],
            potm_name=result["potm_name"],
            potm_reason=result["potm_reason"],
        )
        await send_message(result_msg)

    return result


def _determine_result(
    match_state: MatchState,
    innings1: InningsState,
    innings2: InningsState,
    target: int,
) -> dict:
    """Determine match result from both innings."""
    team1_name = match_state.team1_name
    team2_name = match_state.team2_name
    team1_id = match_state.team1_id
    team2_id = match_state.team2_id

    # Determine which team batted first
    first_bat_id = innings1.batting_team_id
    second_bat_id = innings2.batting_team_id
    first_bat_name = team1_name if first_bat_id == team1_id else team2_name
    second_bat_name = team1_name if second_bat_id == team1_id else team2_name

    if innings2.target_reached:
        # Second team won
        winner_id = second_bat_id
        winner_name = second_bat_name
        loser_id = first_bat_id
        loser_name = first_bat_name
        wickets_remaining = 10 - innings2.total_wickets
        result_type = f"{second_bat_name}_won"
        result_detail = f"won by {wickets_remaining} wicket{'s' if wickets_remaining != 1 else ''}"
    elif innings2.all_out or innings2.is_complete:
        # First team won (or tie)
        first_score = innings1.total_runs
        second_score = innings2.total_runs

        if first_score > second_score:
            winner_id = first_bat_id
            winner_name = first_bat_name
            loser_id = second_bat_id
            loser_name = second_bat_name
            margin = first_score - second_score
            result_type = f"{first_bat_name}_won"
            result_detail = f"won by {margin} run{'s' if margin != 1 else ''}"
        elif first_score == second_score:
            winner_id = 0
            winner_name = "Tie"
            loser_name = "Tie"
            result_type = "tie"
            result_detail = "Match tied!"
        else:
            winner_id = second_bat_id
            winner_name = second_bat_name
            loser_id = first_bat_id
            loser_name = first_bat_name
            margin = second_score - first_score
            result_type = f"{second_bat_name}_won"
            result_detail = f"won by {margin} run{'s' if margin != 1 else ''}"
    else:
        # Shouldn't happen
        winner_id = 0
        winner_name = "No Result"
        loser_name = "No Result"
        result_type = "no_result"
        result_detail = "Match abandoned"

    # POTM: highest impact player
    potm_id, potm_name, potm_reason = _select_potm(innings1, innings2)

    return {
        "winner_id": winner_id,
        "winner_name": winner_name,
        "loser_name": loser_name,
        "result_type": result_type,
        "result_detail": result_detail,
        "innings1_score": f"{innings1.total_runs}/{innings1.total_wickets}",
        "innings2_score": f"{innings2.total_runs}/{innings2.total_wickets}",
        "potm_id": potm_id,
        "potm_name": potm_name,
        "potm_reason": potm_reason,
    }


def _select_potm(innings1: InningsState, innings2: InningsState) -> tuple[str, str, str]:
    """Select Player of the Match based on performance."""
    best_id = ""
    best_name = "Unknown"
    best_reason = "Outstanding performance"
    best_score = 0

    # Check all batters
    for inn in [innings1, innings2]:
        for pid, stat in inn.batting_stats.items():
            if stat.balls > 0:
                # Score: runs * 1.5 + (4s + 6s * 2) + bonus for not out
                score = stat.runs * 1.5 + stat.fours + stat.sixes * 2
                if stat.is_not_out:
                    score *= 1.2
                if score > best_score:
                    best_score = score
                    best_id = pid
                    best_name = stat.name
                    if stat.runs >= 50:
                        best_reason = f"Brilliant {stat.runs}* ({stat.balls}) with {stat.fours} fours and {stat.sixes} sixes"
                    elif stat.runs >= 30:
                        best_reason = f"Excellent {stat.runs}({stat.balls}) with {stat.fours} fours and {stat.sixes} sixes"
                    else:
                        best_reason = f"Key contribution of {stat.runs}({stat.balls})"

    # Check all bowlers
    for inn in [innings1, innings2]:
        for pid, stat in inn.bowling_stats.items():
            if stat.balls_bowled > 0 and stat.wickets > 0:
                # Score: wickets * 25 - runs conceded * 0.3 + bonus for 3+ wickets
                score = stat.wickets * 25 - stat.runs_conceded * 0.3
                if stat.wickets >= 3:
                    score += 20
                if stat.economy < 7:
                    score += 10
                if score > best_score:
                    best_score = score
                    best_id = pid
                    best_name = stat.name
                    best_reason = f"Excellent bowling: {stat.figures} (Econ: {stat.economy:.1f})"

    return best_id, best_name, best_reason
