"""Commentary generator for match simulation.

Generates:
- Ball-by-ball commentary text
- Score updates (every 2 overs)
- Innings break summary
- Match result with scorecards
"""

from __future__ import annotations

import random
from typing import Optional

from app.simulation.match_state import (
    BALLS_PER_OVER,
    BALLS_PER_INNINGS,
    InningsState,
    MatchState,
)


# ── Ball Commentary Templates ─────────────────────────────────────

_DOT_TEMPLATES = [
    "{bowler} to {striker}: dot. {delivery}.",
    "{bowler} to {striker}: no run. {delivery}.",
    "{bowler} to {striker}: defended solidly. {delivery}.",
    "{bowler} to {striker}: played to {region}. No run.",
    "{bowler} to {striker}: left alone. {delivery}.",
    "{bowler} to {striker}: beaten! {delivery}. Great bowling.",
    "{bowler} to {striker}: dot ball. {delivery}. Tight line.",
]

_SINGLE_TEMPLATES = [
    "{bowler} to {striker}: single. {delivery}. Worked to {region}.",
    "{bowler} to {striker}: 1 run. {delivery}. Quick single taken.",
    "{bowler} to {striker}: rotated to {region}. One run.",
    "{bowler} to {striker}: pushed to {region} for a single.",
    "{bowler} to {striker}: flicked off the pads. One run.",
]

_DOUBLE_TEMPLATES = [
    "{bowler} to {striker}: TWO! {delivery}. {region}. Quick running!",
    "{bowler} to {striker}: 2 runs. {delivery}. Good running between the wickets.",
    "{bowler} to {striker}: driven to {region}. Two runs.",
    "{bowler} to {striker}: pushed into the gap for a couple.",
]

_TRIPLE_TEMPLATES = [
    "{bowler} to {striker}: THREE! {delivery}. Great running!",
    "{bowler} to {striker}: 3 runs! Excellent hustle between the wickets.",
    "{bowler} to {striker}: driven to deep {region}. Three runs.",
]

_FOUR_TEMPLATES = [
    "💥 {striker} CRACKS {bowler} for FOUR! {delivery}. {region}!",
    "💥 {striker} FIRES {bowler} for FOUR! {region}! What a shot!",
    "💥 BOUNDARY! {striker} off {bowler}. {delivery}. {region}!",
    "💥 FOUR! {striker} smashes {bowler}. {region}! Racing away!",
    "💥 {striker} off the back foot PUNCHES {bowler} for FOUR through {region}!",
    "💥 {striker} makes room and SLAPS {bowler} for FOUR through {region}!",
]

_SIX_TEMPLATES = [
    "🔥🔥 {striker} MOWES {bowler} for SIX! OVER {region}! MASSIVE!",
    "🔥🔥 SIX! {striker} off {bowler}! {delivery}. {region}! Into the stands!",
    "🔥🔥 {striker} LAUNCHES {bowler} over {region}! SIX! What a hit!",
    "🔥🔥 MASSIVE SIX! {striker} off {bowler}! {region}! That's gone miles!",
    "🔥🔥 {striker} clears the ropes! SIX off {bowler}! {region}!",
    "🔥🔥 UP, UP AND AWAY! {striker} smokes {bowler} for SIX over {region}!",
]

_WICKET_TEMPLATES = [
    "⚡⚡ WICKET! {bowler} gets {striker}! {dismissal_detail} for {runs}({balls})! {extra}",
    "⚡⚡ BREAKTHROUGH! {striker} falls to {bowler}! {dismissal_detail}! {runs}({balls}). {extra}",
    "⚡⚡ GONE! {striker} c/b {bowler}! {dismissal_detail}! {runs}({balls}). {extra}",
    "⚡⚡ THAT'S A BIG WICKET! {striker} {dismissal_type} off {bowler}! {runs}({balls}). {extra}",
    "⚡⚡ {bowler} STRIKES! {striker} gone for {runs}({balls})! {dismissal_detail}!",
]

_FREE_HIT_TEMPLATES = [
    "FREE HIT! {bowler} to {striker}: {result}",
    "🎯 FREE HIT! {striker} faces {bowler}: {result}",
]

_WIDE_TEMPLATES = [
    "WIDE! {bowler} strays down leg. +1 run.",
    "Wide from {bowler}. Too far down leg side. Extra run.",
    "{bowler} bowls wide. The umpire signals wide.",
]

_NOBALL_TEMPLATES = [
    "NO BALL! {bowler} oversteps! Free hit coming up!",
    "No ball from {bowler}! No ball called — free hit next!",
    "{bowler} bowls a no ball! +1 run and a free hit!",
]

_BYE_TEMPLATES = [
    "Bye! {bowler} to {striker}: the ball goes through to the keeper. {runs} bye.",
    "Byes taken. {bowler} beats the bat, {runs} bye.",
]

_LEGBYE_TEMPLATES = [
    "Leg bye! {bowler} to {striker}: deflects off the pad. {runs} leg bye.",
    "Leg bye off the hips. {bowler} to {striker}. {runs} leg bye.",
]


def generate_ball_commentary(
    ball_num: int,
    over_num: int,
    ball_in_over: int,
    striker_name: str,
    bowler_name: str,
    outcome,
    partnership_runs: int = 0,
    partnership_balls: int = 0,
) -> str:
    """Generate commentary for a single ball."""
    result_text = ""
    extra_text = ""

    o = outcome.outcome

    if o == "dot":
        template = random.choice(_DOT_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            delivery=outcome.delivery_type, region=outcome.region,
        )
    elif o == "single":
        template = random.choice(_SINGLE_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            delivery=outcome.delivery_type, region=outcome.region,
        )
    elif o == "double":
        template = random.choice(_DOUBLE_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            delivery=outcome.delivery_type, region=outcome.region,
        )
    elif o == "triple":
        template = random.choice(_TRIPLE_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            delivery=outcome.delivery_type, region=outcome.region,
        )
    elif o == "four":
        template = random.choice(_FOUR_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            delivery=outcome.delivery_type, region=outcome.region,
        )
    elif o == "six":
        template = random.choice(_SIX_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            delivery=outcome.delivery_type, region=outcome.region,
        )
    elif o == "wicket":
        template = random.choice(_WICKET_TEMPLATES)
        extra = ""
        if partnership_runs > 20:
            extra = f"Partnership of {partnership_runs}({partnership_balls}) broken!"
        result_text = template.format(
            bowler=bowler_name, striker=striker_name,
            dismissal_type=outcome.dismissal_type,
            dismissal_detail=outcome.dismissal_detail,
            runs="", balls="", extra=extra,
        )
    elif o == "wide":
        result_text = random.choice(_WIDE_TEMPLATES).format(bowler=bowler_name, striker=striker_name)
    elif o == "noball":
        result_text = random.choice(_NOBALL_TEMPLATES).format(bowler=bowler_name, striker=striker_name)
    elif o == "bye":
        template = random.choice(_BYE_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name, runs=outcome.extras,
        )
    elif o == "legbye":
        template = random.choice(_LEGBYE_TEMPLATES)
        result_text = template.format(
            bowler=bowler_name, striker=striker_name, runs=outcome.extras,
        )

    # Add ball number prefix
    prefix = f"{over_num}.{ball_in_over}"
    return f"`{prefix}` {result_text}"


# ── Score Update (Every 2 Overs) ─────────────────────────────────

def generate_score_update(innings: InningsState, team_name: str) -> str:
    """Generate the formatted score update shown every 2 overs."""
    lines = []

    # Header
    lines.append(f"⚡ **{team_name}**: {innings.total_runs}/{innings.total_wickets} ({innings.overs_display} overs)")
    lines.append("")

    # Phase indicator
    phase_emoji = {"powerplay": "🟢", "middle": "🟡", "death": "🔴"}.get(innings.phase, "⚪")
    lines.append(f"{phase_emoji} Phase: {innings.phase.title()}")

    # Required rate (2nd innings)
    if innings.runs_needed is not None and innings.runs_needed > 0:
        lines.append(f"🎯 Need: {innings.runs_needed} off {innings.balls_remaining} balls")
        lines.append(f"📊 CRR: {innings.run_rate:.2f} | RRR: {innings.required_run_rate:.2f}")
    else:
        lines.append(f"📊 CRR: {innings.run_rate:.2f}")

    lines.append("")

    # Current batters
    lines.append("🏏 **Batting:**")
    for batter_id in [innings.striker_id, innings.non_striker_id]:
        stat = innings.batting_stats.get(batter_id)
        if stat:
            marker = " *" if batter_id == innings.striker_id else ""
            lines.append(f"• {stat.name}{marker}: {stat.runs}* ({stat.balls}) | SR: {stat.strike_rate:.1f}")

    # Partnership
    if innings.partnership.balls > 0:
        lines.append(f"\n🤝 Partnership: {innings.partnership.runs}({innings.partnership.balls})")

    lines.append("")

    # Bowling
    lines.append("💥 **Bowling:**")
    for bowler_id, stat in sorted(
        innings.bowling_stats.items(),
        key=lambda x: x[1].wickets,
        reverse=True,
    ):
        if stat.balls_bowled > 0:
            lines.append(f"• {stat.name}: {stat.figures}")

    # Last wicket
    if innings.total_wickets > 0:
        # Find most recent dismissal
        for batter_id, stat in reversed(list(innings.batting_stats.items())):
            if stat.dismissal_type:
                lines.append(f"\n❌ Last wicket: {stat.name} {stat.dismissal_type} for {stat.runs}({stat.balls})")
                break

    return "\n".join(lines)


# ── Innings Break Summary ─────────────────────────────────────────

def generate_innings_summary(innings: InningsState, team_name: str, target: int) -> str:
    """Generate full innings break summary."""
    lines = []

    lines.append(f"{'='*40}")
    lines.append(f"✅ **INNINGS 1 COMPLETE**")
    lines.append(f"{'='*40}")
    lines.append(f"")
    lines.append(f"🏏 **{team_name}**: {innings.total_runs}/{innings.total_wickets} ({innings.overs_display})")
    lines.append(f"")
    lines.append(f"📊 Run Rate: {innings.run_rate:.2f}")
    lines.append(f"🎯 **TARGET: {target} runs**")
    lines.append(f"")

    # Batting scorecard
    lines.append(f"**BATTING:**")
    lines.append(f"{'─'*35}")
    for batter_id in innings.batting_order:
        stat = innings.batting_stats.get(batter_id)
        if stat and stat.balls > 0:
            not_out = "*" if stat.is_not_out else ""
            dismissal = ""
            if stat.dismissal_type:
                dismissal = f" {stat.dismissal_type}"
            lines.append(
                f"  {stat.name}{not_out}  {stat.runs}({stat.balls})  4s:{stat.fours} 6s:{stat.sixes}  SR:{stat.strike_rate:.1f}{dismissal}"
            )
    lines.append(f"{'─'*35}")
    lines.append(f"  **TOTAL: {innings.total_runs}/{innings.total_wickets}** ({innings.overs_display})")

    # Extras
    lines.append(f"  Extras: {innings.total_extras} (W:{innings.wides} NB:{innings.noballs} B:{innings.byes} LB:{innings.legbyes})")

    # Bowling
    lines.append(f"")
    lines.append(f"**BOWLING:**")
    lines.append(f"{'─'*35}")
    for bowler_id, stat in sorted(
        innings.bowling_stats.items(),
        key=lambda x: x[1].wickets,
        reverse=True,
    ):
        if stat.balls_bowled > 0:
            lines.append(f"  {stat.name}: {stat.figures}  Econ: {stat.economy:.2f}")

    return "\n".join(lines)


# ── Match Result ──────────────────────────────────────────────────

def generate_match_result(
    match_state: MatchState,
    winning_team_name: str,
    losing_team_name: str,
    result_type: str,
    result_detail: str,
    potm_name: str,
    potm_reason: str,
) -> str:
    """Generate the final match result message."""
    lines = []

    lines.append(f"{'='*40}")
    lines.append(f"🏆 **MATCH RESULT**")
    lines.append(f"{'='*40}")
    lines.append(f"")
    lines.append(f"**{winning_team_name}** {result_detail}!")
    lines.append(f"")

    # POTM
    lines.append(f"⭐ **Player of the Match:** {potm_name}")
    lines.append(f"   {potm_reason}")
    lines.append(f"")

    # Innings 1 scorecard
    if match_state.innings1:
        inn = match_state.innings1
        bat_team = match_state.team1_name if inn.batting_team_id == match_state.team1_id else match_state.team2_name
        bowl_team = match_state.team2_name if inn.bowling_team_id == match_state.team2_id else match_state.team1_name

        lines.append(f"{'─'*40}")
        lines.append(f"**INNINGS 1 — {bat_team}**")
        lines.append(f"{'─'*40}")
        lines.append(f"**{bat_team}**: {inn.total_runs}/{inn.total_wickets} ({inn.overs_display})")
        lines.append(f"")
        lines.append(f"**Batting:**")
        for batter_id in inn.batting_order:
            stat = inn.batting_stats.get(batter_id)
            if stat and stat.balls > 0:
                not_out = "*" if stat.is_not_out else ""
                lines.append(f"  {stat.name}{not_out}  {stat.runs}({stat.balls})  4s:{stat.fours} 6s:{stat.sixes}  SR:{stat.strike_rate:.1f}")
        lines.append(f"  Extras: {inn.total_extras}")
        lines.append(f"")
        lines.append(f"**Bowling:**")
        for bid, stat in inn.bowling_stats.items():
            if stat.balls_bowled > 0:
                lines.append(f"  {stat.name}: {stat.figures}  Econ: {stat.economy:.2f}")
        lines.append(f"")

    # Innings 2 scorecard
    if match_state.innings2:
        inn = match_state.innings2
        bat_team = match_state.team1_name if inn.batting_team_id == match_state.team1_id else match_state.team2_name

        lines.append(f"{'─'*40}")
        lines.append(f"**INNINGS 2 — {bat_team}**")
        lines.append(f"{'─'*40}")
        lines.append(f"**{bat_team}**: {inn.total_runs}/{inn.total_wickets} ({inn.overs_display})")
        lines.append(f"")
        lines.append(f"**Batting:**")
        for batter_id in inn.batting_order:
            stat = inn.batting_stats.get(batter_id)
            if stat and stat.balls > 0:
                not_out = "*" if stat.is_not_out else ""
                lines.append(f"  {stat.name}{not_out}  {stat.runs}({stat.balls})  4s:{stat.fours} 6s:{stat.sixes}  SR:{stat.strike_rate:.1f}")
        lines.append(f"  Extras: {inn.total_extras}")
        lines.append(f"")
        lines.append(f"**Bowling:**")
        for bid, stat in inn.bowling_stats.items():
            if stat.balls_bowled > 0:
                lines.append(f"  {stat.name}: {stat.figures}  Econ: {stat.economy:.2f}")

    return "\n".join(lines)


# ── Venue Intro ───────────────────────────────────────────────────

def generate_venue_intro(venue: dict) -> str:
    """Generate venue introduction before match starts."""
    return (
        f"🏟 **{venue['name']}**\n\n"
        f"{venue['description']}\n\n"
        f"Expected first innings score: ~{venue['avg_first_innings']} runs"
    )


# ── Toss ──────────────────────────────────────────────────────────

def generate_toss_result(
    toss_winner_name: str,
    decision: str,
    venue_name: str,
) -> str:
    """Generate toss result message."""
    action = "bat first" if decision == "bat" else "bowl first"
    return (
        f"🪙 **TOSS at {venue_name}**\n\n"
        f"**{toss_winner_name}** win the toss and choose to **{action}**."
    )


# ── Innings Start ─────────────────────────────────────────────────

def generate_innings_start(
    innings_number: int,
    batting_team: str,
    bowling_team: str,
    target: Optional[int] = None,
) -> str:
    """Generate innings start message."""
    lines = []
    if innings_number == 1:
        lines.append(f"🔴 **INNINGS 1**")
        lines.append(f"")
        lines.append(f"🏏 **{batting_team}** to bat")
        lines.append(f"⚾ **{bowling_team}** to bowl")
    else:
        lines.append(f"🔴 **INNINGS 2 — CHASE**")
        lines.append(f"")
        lines.append(f"🏏 **{batting_team}** to bat (need {target} runs)")
        lines.append(f"⚾ **{bowling_team}** to bowl")

    return "\n".join(lines)
