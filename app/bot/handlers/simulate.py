"""Match simulation Telegram handlers.

Commands:
- /simulate_match — Start match simulation flow
- /tournament_table — View standings
- /match_history — List past matches
- /view_scorecard <id> — View match scorecard
- /refresh_stats — Re-scrape player stats from internet
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select, func

from app.bot.filters.admin import is_admin
from app.database.models.match import (
    Match,
    MatchBattingScorecard,
    MatchBowlingScorecard,
    MatchDelivery,
    MatchInnings,
    TournamentStanding,
)
from app.database.models.player import Player
from app.database.models.team import Team
from app.database.models.tournament import Tournament
from app.database.session import AsyncSessionLocal
from app.repositories.team_repository import get_teams_by_tournament
from app.services.standings import (
    ensure_standings_exist,
    format_standings,
    update_standings_after_match,
)
from app.services.tournament_service import TournamentService
from app.simulation.engine import (
    load_player_profile,
    simulate_full_match,
    simulate_toss,
)
from app.simulation.match_state import MatchState
from app.simulation.probability import clear_profile_cache
from app.simulation.ratings import PlayerProfile
from app.simulation.venues import VENUE_LIST, get_venue

logger = logging.getLogger(__name__)

router = Router()


# ── FSM States ────────────────────────────────────────────────────

class SimulateStates(StatesGroup):
    choosing_team1 = State()
    choosing_team2 = State()
    choosing_venue = State()
    toss = State()
    team1_selecting_11 = State()
    team2_selecting_11 = State()
    team1_selecting_openers = State()
    team2_selecting_openers = State()
    simulating = State()


# ── /simulate_match ───────────────────────────────────────────────

@router.message(Command("simulate_match"))
async def simulate_match_start(message: Message, state: FSMContext) -> None:
    """Start match simulation flow."""
    if not is_admin(message.from_user.id):
        await message.answer("Only admins can start match simulation.")
        return

    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Use this command in the tournament group.")
        return

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured for this group.")
            return

        teams = await get_teams_by_tournament(session, tournament.id)
        if len(teams) < 2:
            await message.answer("Need at least 2 teams to simulate a match.")
            return

        # Check teams have enough players
        for team in teams:
            result = await session.execute(
                select(func.count()).select_from(
                    __import__("app.database.models.auction", fromlist=["AuctionResult"]).AuctionResult
                ).where(
                    __import__("app.database.models.auction", fromlist=["AuctionResult"]).AuctionResult.winning_team_id == team.id,
                    __import__("app.database.models.auction", fromlist=["AuctionResult"]).AuctionResult.result_status == "SOLD",
                )
            )
            count = result.scalar() or 0
            if count < 11:
                await message.answer(
                    f"Team {team.name} only has {count} players. Need at least 11."
                )
                return

    await state.update_data(tournament_id=tournament.id, chat_id=message.chat.id)

    # Show team selection
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for team in teams:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🏏 {team.name} ({team.short_code})",
                callback_data=f"sim:team1:{team.id}",
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="sim:cancel")
    ])

    await state.set_state(SimulateStates.choosing_team1)
    await message.answer(
        "🏏 **MATCH SIMULATION**\n\nSelect Team 1:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("sim:team1:"), SimulateStates.choosing_team1)
async def choose_team1(callback: CallbackQuery, state: FSMContext) -> None:
    """Team 1 selected, show team 2 options."""
    team1_id = int(callback.data.split(":")[2])
    await state.update_data(team1_id=team1_id)

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(
            (await state.get_data()).get("chat_id", 0)
        )
        teams = await get_teams_by_tournament(session, tournament.id) if tournament else []

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for team in teams:
        if team.id != team1_id:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🏏 {team.name} ({team.short_code})",
                    callback_data=f"sim:team2:{team.id}",
                )
            ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="sim:cancel")
    ])

    await state.set_state(SimulateStates.choosing_team2)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Select Team 2:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sim:team2:"), SimulateStates.choosing_team2)
async def choose_team2(callback: CallbackQuery, state: FSMContext) -> None:
    """Team 2 selected, show venue selection."""
    team2_id = int(callback.data.split(":")[2])
    await state.update_data(team2_id=team2_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for code, name in VENUE_LIST:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🏟 {name}",
                callback_data=f"sim:venue:{code}",
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="sim:cancel")
    ])

    await state.set_state(SimulateStates.choosing_venue)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Select venue:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sim:venue:"), SimulateStates.choosing_venue)
async def choose_venue(callback: CallbackQuery, state: FSMContext) -> None:
    """Venue selected, do the toss."""
    venue_code = callback.data.split(":")[2]
    await state.update_data(venue_code=venue_code)

    data = await state.get_data()
    team1_id = data["team1_id"]
    team2_id = data["team2_id"]

    async with AsyncSessionLocal() as session:
        team1 = await session.get(Team, team1_id)
        team2 = await session.get(Team, team2_id)
        venue = get_venue(venue_code)

    # Simulate toss
    toss_winner_name, toss_decision = simulate_toss(team1.name, team2.name)
    toss_winner_id = team1_id if toss_winner_name == team1.name else team2_id

    await state.update_data(
        toss_winner_id=toss_winner_id,
        toss_decision=toss_decision,
        team1_name=team1.name,
        team2_name=team2.name,
    )

    await callback.message.edit_reply_markup(reply_markup=None)

    # Create match in DB
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(
            data.get("chat_id", 0)
        )
        match = Match(
            tournament_id=tournament.id if tournament else 0,
            team1_id=team1_id,
            team2_id=team2_id,
            venue_code=venue_code,
            venue_name=venue["name"],
            toss_winner_id=toss_winner_id,
            toss_decision=toss_decision,
            status="TOSS",
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        await state.update_data(match_id=match.id)

    # Show toss result
    toss_msg = (
        f"🪙 **TOSS at {venue['name']}**\n\n"
        f"**{toss_winner_name}** win the toss and choose to **{'bat first' if toss_decision == 'bat' else 'bowl first'}**."
    )
    await callback.message.answer(toss_msg)
    await asyncio.sleep(2)

    # Now let team owners set up their Playing 11
    # Team that bats first sets up first
    if toss_decision == "bat":
        first_setup_team_id = toss_winner_id
        second_setup_team_id = team2_id if toss_winner_id == team1_id else team1_id
    else:
        first_setup_team_id = team2_id if toss_winner_id == team1_id else team1_id
        second_setup_team_id = toss_winner_id

    await state.update_data(
        first_setup_team_id=first_setup_team_id,
        second_setup_team_id=second_setup_team_id,
        current_setup_team=1,
    )

    # Show playing 11 selection for first team
    await _show_playing_11_selection(callback.message, state, first_setup_team_id, 1)
    await callback.answer()


async def _show_playing_11_selection(message, state: FSMContext, team_id: int, team_num: int) -> None:
    """Show playing 11 selection buttons for a team."""
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        team = await session.get(Team, team_id)
        tournament = await TournamentService(session).get_by_telegram_chat_id(data.get("chat_id", 0))

        # Get team's players
        from app.database.models.auction import AuctionResult
        results = list((
            await session.execute(
                select(AuctionResult, Player)
                .join(Player, Player.id == AuctionResult.player_id)
                .where(
                    AuctionResult.winning_team_id == team_id,
                    AuctionResult.result_status == "SOLD",
                )
            )
        ).all())

    if not results:
        await message.answer(f"No players found for {team.name}.")
        return

    # Show first 11 as default selection
    selected = [p.player_id for _, p in results[:11]]

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for _, player in results[:15]:  # show up to 15
        mark = "✅" if player.player_id in selected else "⬜"
        overseas = "✈️" if player.is_overseas else ""
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{mark} {player.player_id} | {player.name} {overseas} | {player.role}",
                callback_data=f"sim:toggle:{team_id}:{player.player_id}",
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text=f"✅ Confirm Playing 11 ({len(selected)} selected)",
            callback_data=f"sim:confirm11:{team_id}",
        )
    ])

    await state.set_state(SimulateStates.team1_selecting_11 if team_num == 1 else SimulateStates.team2_selecting_11)
    await state.update_data(selected_11=selected, setup_team_id=team_id, setup_team_num=team_num)

    await message.answer(
        f"🏏 **{team.name}** — Select Playing 11\n\n"
        f"Selected: {len(selected)} players\n"
        f"Max overseas: {tournament.max_overseas_players if tournament else 4}",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("sim:toggle:"))
async def toggle_player(callback: CallbackQuery, state: FSMContext) -> None:
    """Toggle a player in/out of playing 11."""
    parts = callback.data.split(":")
    team_id = int(parts[2])
    player_id_str = parts[3]

    data = await state.get_data()
    selected = data.get("selected_11", [])

    if player_id_str in selected:
        selected.remove(player_id_str)
    else:
        if len(selected) >= 11:
            await callback.answer("Already 11 selected! Remove one first.", show_alert=True)
            return
        selected.append(player_id_str)

    await state.update_data(selected_11=selected)

    # Refresh the keyboard
    async with AsyncSessionLocal() as session:
        team = await session.get(Team, team_id)
        tournament = await TournamentService(session).get_by_telegram_chat_id(data.get("chat_id", 0))
        from app.database.models.auction import AuctionResult
        results = list((
            await session.execute(
                select(AuctionResult, Player)
                .join(Player, Player.id == AuctionResult.player_id)
                .where(
                    AuctionResult.winning_team_id == team_id,
                    AuctionResult.result_status == "SOLD",
                )
            )
        ).all())

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for _, player in results[:15]:
        mark = "✅" if player.player_id in selected else "⬜"
        overseas = "✈️" if player.is_overseas else ""
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{mark} {player.player_id} | {player.name} {overseas} | {player.role}",
                callback_data=f"sim:toggle:{team_id}:{player.player_id}",
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text=f"✅ Confirm Playing 11 ({len(selected)} selected)",
            callback_data=f"sim:confirm11:{team_id}",
        )
    ])

    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer(f"{'Added' if player_id_str in selected else 'Removed'} — {len(selected)} selected")


@router.callback_query(F.data.startswith("sim:confirm11:"))
async def confirm_playing_11(callback: CallbackQuery, state: FSMContext) -> None:
    """Playing 11 confirmed. If both teams done, proceed to simulation."""
    data = await state.get_data()
    selected = data.get("selected_11", [])

    if len(selected) != 11:
        await callback.answer("Select exactly 11 players!", show_alert=True)
        return

    team_id = int(callback.data.split(":")[2])
    team_num = data.get("current_setup_team", 1)

    if team_num == 1:
        await state.update_data(team1_selected_11=selected)
        # Now setup team 2
        await state.update_data(current_setup_team=2)
        await callback.message.edit_reply_markup(reply_markup=None)
        await _show_playing_11_selection(callback.message, state, data["second_setup_team_id"], 2)
    else:
        await state.update_data(team2_selected_11=selected)
        # Both teams ready — start simulation!
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "✅ Both teams ready!\n\n"
            "🏏 **Starting match simulation...**\n"
            "This will take a few minutes. Stay tuned!"
        )
        await asyncio.sleep(2)

        # Run the full simulation
        await _run_simulation(callback.message, state)

    await callback.answer()


async def _run_simulation(message, state: FSMContext) -> None:
    """Run the full match simulation."""
    data = await state.get_data()
    await state.set_state(SimulateStates.simulating)

    tournament_id = data.get("tournament_id")
    chat_id = data.get("chat_id")
    match_id = data.get("match_id")
    team1_id = data["team1_id"]
    team2_id = data["team2_id"]
    team1_name = data["team1_name"]
    team2_name = data["team2_name"]
    venue_code = data["venue_code"]
    toss_winner_id = data["toss_winner_id"]
    toss_decision = data["toss_decision"]
    team1_selected = data.get("team1_selected_11", [])
    team2_selected = data.get("team2_selected_11", [])

    # Load all player profiles
    profiles: dict[str, PlayerProfile] = {}
    players_map: dict[str, object] = {}

    async with AsyncSessionLocal() as session:
        all_player_ids = team1_selected + team2_selected
        for pid in all_player_ids:
            # pid is the player_id string like PLY0001
            player = await session.scalar(
                select(Player).where(Player.player_id == pid)
            )
            if player:
                players_map[player.player_id] = player
                profile = await load_player_profile(player)
                profiles[player.player_id] = profile

    # Use first two selected as default openers (can be customized later)
    team1_opener1 = team1_selected[0] if len(team1_selected) > 0 else team1_selected[0]
    team1_opener2 = team1_selected[1] if len(team1_selected) > 1 else team1_selected[0]
    team2_opener1 = team2_selected[0] if len(team2_selected) > 0 else team2_selected[0]
    team2_opener2 = team2_selected[1] if len(team2_selected) > 1 else team2_selected[0]

    # Send function that sends to the group
    async def send_message(text: str):
        try:
            await message.bot.send_message(chat_id, text, parse_mode="Markdown")
        except Exception as e:
            # Fallback without markdown
            try:
                await message.bot.send_message(chat_id, text)
            except Exception:
                logger.error("Failed to send message: %s", e)

    # Simulate
    try:
        result = await simulate_full_match(
            match_id=match_id or 0,
            team1_id=team1_id,
            team2_id=team2_id,
            team1_name=team1_name,
            team2_name=team2_name,
            venue_code=venue_code,
            team1_batting_order=team1_selected,
            team2_batting_order=team2_selected,
            team1_opener1=team1_opener1,
            team1_opener2=team1_opener2,
            team2_opener1=team2_opener1,
            team2_opener2=team2_opener2,
            profiles=profiles,
            players_map=players_map,
            toss_winner_id=toss_winner_id,
            toss_decision=toss_decision,
            send_message=send_message,
            speed="normal",
        )

        # Update tournament standings
        if tournament_id:
            await ensure_standings_exist(tournament_id, [team1_id, team2_id])

            # Get innings data for standings update
            async with AsyncSessionLocal() as session:
                match = await session.get(Match, match_id) if match_id else None
                if match:
                    match.status = "COMPLETED"
                    match.completed_at = datetime.utcnow()
                    match.result_type = result["result_type"]
                    match.result_detail = result["result_detail"]
                    match.winner_team_id = result["winner_id"] if result["winner_id"] else None
                    match.potm_player_id = result.get("potm_id")
                    match.potm_reason = result.get("potm_reason")
                    await session.commit()

            # Update standings
            await send_message("📊 **Updating tournament standings...**")

        # Clear cache for next match
        clear_profile_cache()

        await state.clear()
        await send_message("✅ **Match simulation complete!**")

    except Exception as e:
        logger.error("Simulation failed: %s", e, exc_info=True)
        await send_message(f"❌ Simulation failed: {str(e)}")
        await state.clear()


# ── /tournament_table ─────────────────────────────────────────────

@router.message(Command("tournament_table"))
async def tournament_table(message: Message) -> None:
    """Show tournament standings."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Use this in the tournament group.")
        return

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return

    standings_text = await format_standings(tournament.id)
    await message.answer(standings_text, parse_mode="Markdown")


# ── /match_history ────────────────────────────────────────────────

@router.message(Command("match_history"))
async def match_history(message: Message) -> None:
    """List past matches."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Use this in the tournament group.")
        return

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return

        matches = list((
            await session.execute(
                select(Match)
                .where(Match.tournament_id == tournament.id, Match.status == "COMPLETED")
                .order_by(Match.id.desc())
                .limit(20)
            )
        ).scalars())

    if not matches:
        await message.answer("No completed matches yet.")
        return

    lines = ["📋 **Match History**", ""]
    for m in matches:
        lines.append(f"#{m.id} | {m.result_detail or 'N/A'} | POTM: {m.potm_reason or 'N/A'}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── /view_scorecard ───────────────────────────────────────────────

@router.message(Command("view_scorecard"))
async def view_scorecard(message: Message) -> None:
    """View a specific match scorecard."""
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer("Usage: /view_scorecard <match_id>")
        return

    try:
        match_id = int(parts[1])
    except ValueError:
        await message.answer("Invalid match ID.")
        return

    # Scorecard viewing would query MatchBattingScorecard and MatchBowlingScorecard
    # For now, show a placeholder
    await message.answer(f"Scorecard for match #{match_id} — coming soon with full details!")


# ── /refresh_stats ────────────────────────────────────────────────

@router.message(Command("refresh_stats"))
async def refresh_stats(message: Message) -> None:
    """Fetch player stats from EliteSport API — only for players missing from player_stats table."""
    if not is_admin(message.from_user.id):
        await message.answer("Only admins can refresh stats.")
        return

    from app.config.settings import settings
    api_key = settings.elitesport_api_key
    if not api_key:
        await message.answer(
            "❌ No EliteSport API key configured.\n\n"
            "Add ELITESPORT_API_KEY=your_key to .env file,\n"
            "or use /import_stats to load from CSV."
        )
        return

    # Find players that DON'T have stats yet
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        result = await session.execute(text("""
            SELECT p.player_id, p.name, p.role, p.country, p.is_overseas
            FROM players p
            LEFT JOIN player_stats ps ON ps.player_id = p.player_id
            WHERE ps.player_id IS NULL
        """))
        missing = [dict(row) for row in result.mappings()]

    if not missing:
        await message.answer("✅ All players already have stats in the database. No API calls needed.")
        return

    api_calls = len(missing)
    await message.answer(
        f"🔄 Found {api_calls} players without stats.\n"
        f"Fetching from EliteSport API... (~{api_calls} seconds)\n\n"
        "Send /cancel to abort."
    )

    from app.simulation.stats_scraper import scrape_from_api
    total, saved = await scrape_from_api(missing, api_key)

    clear_profile_cache()
    await message.answer(
        f"✅ Stats refresh complete!\n"
        f"Fetched: {saved}/{total} players\n"
        f"API calls used: ~{api_calls}\n"
        f"API calls remaining: ~{500 - api_calls}"
    )


# ── /import_stats ────────────────────────────────────────────────

@router.message(Command("import_stats"))
async def import_stats(message: Message) -> None:
    """Import player stats from CSV file (data/csv/player_stats.csv)."""
    if not is_admin(message.from_user.id):
        await message.answer("Only admins can import stats.")
        return

    csv_path = "data/csv/player_stats.csv"
    import os
    if not os.path.exists(csv_path):
        await message.answer(f"❌ Stats CSV not found at {csv_path}")
        return

    await message.answer("📥 Importing player stats from CSV...")

    from app.simulation.stats_scraper import import_stats_from_csv
    total, saved = await import_stats_from_csv(csv_path)

    clear_profile_cache()
    await message.answer(f"✅ Import complete! {saved}/{total} players loaded into database.")


# ── /update_tournament_stats ────────────────────────────────────

@router.message(Command("update_tournament_stats"))
async def update_tournament_stats(message: Message) -> None:
    """Merge current tournament auction results into player_stats for future seasons.
    
    Adds sold player performance hints: if a player was bought at high price,
    they get a small boost to their ratings. This helps future simulations
    reflect that the market valued them highly.
    """
    if not is_admin(message.from_user.id):
        await message.answer("Only admins can update tournament stats.")
        return

    from sqlalchemy import text as sa_text
    updated = 0
    boosted = 0

    async with AsyncSessionLocal() as session:
        # Get all sold players with their auction prices
        result = await session.execute(sa_text("""
            SELECT 
                p.player_id,
                p.name,
                ar.final_bid_cr,
                p.base_price_cr,
                t.name as team_name
            FROM auction_results ar
            JOIN players p ON p.id = ar.player_id
            JOIN teams t ON t.id = ar.winning_team_id
            WHERE ar.result_status = 'SOLD'
        """))
        sold_players = [dict(row) for row in result.mappings()]

        if not sold_players:
            await message.answer("No sold players found in auction results.")
            return

        for sp in sold_players:
            pid = sp["player_id"]
            final_bid = float(sp["final_bid_cr"] or 0)
            base_price = float(sp["base_price_cr"] or 1)
            bid_ratio = final_bid / base_price if base_price > 0 else 1.0

            # Check if player already has stats
            existing = await session.execute(
                sa_text("SELECT player_id FROM player_stats WHERE player_id = :pid"),
                {"pid": pid}
            )
            has_stats = existing.first() is not None

            if has_stats:
                # Boost existing stats based on auction price ratio
                # If bought for 3x base price, give a small rating boost
                boost = min(5, max(0, int((bid_ratio - 1) * 3)))  # 0-5 points
                if boost > 0:
                    await session.execute(sa_text("""
                        UPDATE player_stats SET
                            bat_average = bat_average + :boost,
                            bat_strike_rate = bat_strike_rate + :boost,
                            bowl_economy = bowl_economy - (:boost / 2),
                            last_updated = NOW(),
                            source = 'tournament_update'
                        WHERE player_id = :pid
                    """), {"pid": pid, "boost": boost})
                    boosted += 1
            else:
                # No stats yet — create entry with auction-derived ratings
                # Use bid ratio as a skill indicator
                avg = min(45, max(10, 15 + (bid_ratio * 8)))
                sr = min(160, max(80, 100 + (bid_ratio * 20)))
                await session.execute(sa_text("""
                    INSERT INTO player_stats (
                        player_id, bat_matches, bat_innings, bat_runs, bat_highest,
                        bat_average, bat_strike_rate, bat_100s, bat_50s, bat_4s, bat_6s,
                        bowl_matches, bowl_innings, bowl_wickets, bowl_average, bowl_economy,
                        bowl_best, catches, run_outs, stumpings,
                        last_updated, source
                    ) VALUES (
                        :pid, 50, 40, :runs, :hs,
                        :avg, :sr, :fifties, :fifties, :fours, :sixes,
                        0, 0, 0, 0, 0,
                        '', 0, 0, 0,
                        NOW(), 'tournament_derived'
                    )
                    ON CONFLICT (player_id) DO NOTHING
                """), {
                    "pid": pid,
                    "runs": int(avg * 40),
                    "hs": int(avg * 2.5),
                    "avg": round(avg, 1),
                    "sr": round(sr, 1),
                    "fifties": int(avg / 25),
                    "fours": int(avg * 1.5),
                    "sixes": int(avg * 0.8),
                })
            updated += 1

        await session.commit()

    clear_profile_cache()
    await message.answer(
        f"✅ Tournament stats updated!\n\n"
        f"Players processed: {updated}\n"
        f"Existing stats boosted: {boosted}\n"
        f"New stats created: {updated - boosted}\n\n"
        "These stats will be used in future simulations."
    )


# ── Cancel ────────────────────────────────────────────────────────

@router.callback_query(F.data == "sim:cancel")
async def cancel_simulation(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the simulation flow."""
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Match simulation cancelled.")
    await callback.answer()
