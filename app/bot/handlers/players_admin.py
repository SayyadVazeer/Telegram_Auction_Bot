import logging
import os
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select

from app.bot.filters.admin import AdminFilter
from app.services.admin_service import add_admin, remove_admin, get_admin_ids
from app.database.session import AsyncSessionLocal
from app.database.models.auction import AuctionResult
from app.database.models.player import Player
from app.repositories.team_repository import get_team_by_owner, get_teams_by_tournament
from app.services.tournament_service import TournamentService
from app.utils.enums import AuctionResultStatus

router = Router()


# -- player_image_change_generator --

@router.message(Command("player_image_change_generator"), AdminFilter())
async def player_image_change_generator(message: Message) -> None:
    """Send player photos and automatically save telegram_file_id."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player).order_by(Player.id))
        players = list(result.scalars().all())
    if not players:
        await message.answer("No players found in the database.")
        return
    sent_count = 0
    saved_count = 0
    skipped_count = 0
    for player in players:
        if player.telegram_file_id:
            skipped_count += 1
            continue
        photo_path = player.telegram_photo_path
        logging.info("Player %s: photo_path=%s, exists=%s", player.player_id, photo_path, os.path.exists(photo_path) if photo_path else "N/A")
        if not photo_path or not os.path.exists(photo_path):
            skipped_count += 1
            continue
        try:
            with open(photo_path, "rb") as f:
                photo_bytes = f.read()
            sent = await message.answer_photo(
                photo=BufferedInputFile(photo_bytes, filename=os.path.basename(photo_path)),
                caption=f"{player.name} ({player.player_id})",
            )
            sent_count += 1
            if sent.photo:
                file_id = sent.photo[-1].file_id
                async with AsyncSessionLocal() as session:
                    db_player = await session.get(Player, player.id)
                    if db_player:
                        db_player.telegram_file_id = file_id
                        await session.commit()
                        saved_count += 1
        except Exception as e:
            logging.warning("Failed for %s: %s", player.player_id, e)
            skipped_count += 1
    summary = (
        f"Upload complete!\n\n"
        f"Photos sent: {sent_count}\n"
        f"File IDs saved: {saved_count}\n"
        f"Skipped: {skipped_count}"
    )
    await message.answer(summary)


# -- save_player_file_id (manual reply method) --

@router.message(AdminFilter(), F.reply_to_message.photo)
async def save_player_file_id(message: Message) -> None:
    """Save telegram_file_id when admin replies to a photo with the player ID."""
    if not message.text or not message.reply_to_message or not message.reply_to_message.photo:
        return
    player_id_text = message.text.strip()
    photo = message.reply_to_message.photo[-1]
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player).where(Player.player_id == player_id_text))
        player = result.scalar_one_or_none()
        if player is None:
            await message.answer(f"\u274c No player: {player_id_text}")
            return
        player.telegram_file_id = photo.file_id
        await session.commit()
    await message.answer(f"\u2705 Saved file_id for {player.name}")


# -- swap_player --

class SwapPlayer(StatesGroup):
    waiting_for_from_player = State()
    waiting_for_to_team = State()
    waiting_for_to_player = State()
    waiting_for_confirm = State()


swap_states = SwapPlayer


@router.message(Command("swap_player"))
async def swap_player_start(message: Message, state: FSMContext) -> None:
    """Initiate a player swap between two teams."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    if message.from_user is None:
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament is configured for this group.")
            return
        team = await get_team_by_owner(session, tournament.id, message.from_user.id)
        if not team:
            await message.answer("You are not registered as a team owner.")
            return
        result = await session.execute(
            select(AuctionResult, Player)
            .join(Player, Player.id == AuctionResult.player_id)
            .where(
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        players = [(r, p) for r, p in result.all()]
    if not players:
        await message.answer("\u274c No players to swap.")
        return
    await state.clear()
    await state.update_data(
        from_team_id=team.id,
        from_team_name=team.name,
        from_team_code=team.short_code,
    )
    player_list = "\n".join(
        f"{i+1}. {p.name} {'(Overseas)' if p.is_overseas else ''} -- Rs.{Decimal(str(r.final_bid_cr)):.2f} Cr"
        for i, (r, p) in enumerate(players)
    )
    await state.update_data(players=players)
    await state.set_state(swap_states.waiting_for_from_player)
    msg = f"Your team: {team.name} ({team.short_code})\n\nYour players:\n{player_list}\n\nEnter the player number to swap (e.g., 1):"
    await message.answer(msg)


@router.message(swap_states.waiting_for_from_player)
async def swap_select_from_player(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    players = data["players"]
    try:
        idx = int((message.text or "").strip()) - 1
        if idx < 0 or idx >= len(players):
            raise ValueError
    except ValueError:
        await message.answer(f"Enter a number between 1 and {len(players)}.")
        return
    _, selected_player = players[idx]
    await state.update_data(from_player_id=selected_player.id, from_player_name=selected_player.name)
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        teams = await get_teams_by_tournament(session, tournament.id)
    other_teams = [t for t in teams if t.id != data["from_team_id"]]
    if not other_teams:
        await state.clear()
        await message.answer("\u274c No other teams.")
        return
    team_list = "\n".join(f"{i+1}. {t.name} ({t.short_code})" for i, t in enumerate(other_teams))
    await state.update_data(other_teams=other_teams)
    await state.set_state(swap_states.waiting_for_to_team)
    msg = f"Swapping: {selected_player.name}\n\nSelect the team to swap with:\n{team_list}\n\nEnter the team number:"
    await message.answer(msg)


@router.message(swap_states.waiting_for_to_team)
async def swap_select_to_team(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    other_teams = data["other_teams"]
    try:
        idx = int((message.text or "").strip()) - 1
        if idx < 0 or idx >= len(other_teams):
            raise ValueError
    except ValueError:
        await message.answer(f"Enter a number between 1 and {len(other_teams)}.")
        return
    to_team = other_teams[idx]
    await state.update_data(to_team_id=to_team.id, to_team_name=to_team.name, to_team_code=to_team.short_code)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuctionResult, Player)
            .join(Player, Player.id == AuctionResult.player_id)
            .where(
                AuctionResult.winning_team_id == to_team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        to_players = [(r, p) for r, p in result.all()]
    if not to_players:
        await state.clear()
        await message.answer(f"{to_team.name} has no players to swap.")
        return
    player_list = "\n".join(
        f"{i+1}. {p.name} {'(Overseas)' if p.is_overseas else ''} -- Rs.{Decimal(str(r.final_bid_cr)):.2f} Cr"
        for i, (r, p) in enumerate(to_players)
    )
    await state.update_data(to_players=to_players)
    await state.set_state(swap_states.waiting_for_to_player)
    msg = f"{to_team.name} ({to_team.short_code}) players:\n{player_list}\n\nEnter the player number to swap with:"
    await message.answer(msg)


@router.message(swap_states.waiting_for_to_player)
async def swap_select_to_player(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    to_players = data["to_players"]
    try:
        idx = int((message.text or "").strip()) - 1
        if idx < 0 or idx >= len(to_players):
            raise ValueError
    except ValueError:
        await message.answer(f"Enter a number between 1 and {len(to_players)}.")
        return
    _, selected_player = to_players[idx]
    await state.update_data(to_player_id=selected_player.id, to_player_name=selected_player.name)
    await state.set_state(swap_states.waiting_for_confirm)
    msg = (
        f"Swap Confirmation:\n\n"
        f"{data['from_team_name']} ({data['from_team_code']}) gives: {data['from_player_name']}\n"
        f"{data['to_team_name']} ({data['to_team_code']}) gives: {selected_player.name}\n\n"
        "Type yes to confirm or no to cancel."
    )
    await message.answer(msg)


@router.message(swap_states.waiting_for_confirm)
async def swap_confirm(message: Message, state: FSMContext) -> None:
    answer = (message.text or "").strip().lower()
    if answer != "yes":
        await state.clear()
        await message.answer("\u274c Swap cancelled.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        result1 = await session.execute(
            select(AuctionResult).where(
                AuctionResult.player_id == data["from_player_id"],
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        ar1 = result1.scalar_one_or_none()
        result2 = await session.execute(
            select(AuctionResult).where(
                AuctionResult.player_id == data["to_player_id"],
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        ar2 = result2.scalar_one_or_none()
        if ar1 and ar2:
            ar1.winning_team_id = data["to_team_id"]
            ar2.winning_team_id = data["from_team_id"]
            await session.commit()
            msg = (
                f"Swap completed!\n\n"
                f"{data['from_team_name']}: {data['from_player_name']} -> {data['to_team_name']}\n"
                f"{data['to_team_name']}: {data['to_player_name']} -> {data['from_team_name']}"
            )
            await message.answer(msg)
        else:
            await message.answer("\u274c Swap failed: player not found.")
    await state.clear()


# -- /add_admin, /remove_admin, /list_admins --

@router.message(Command("add_admin"))
async def add_admin_command(message: Message) -> None:
    if message.from_user.id not in get_admin_ids():
        await message.answer("Only existing admins can add new admins.")
        return
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        if add_admin(target.id):
            await message.answer(f"Admin added: {target.username or target.full_name} (ID: {target.id})")
        else:
            await message.answer("User is already an admin.")
        return
    parts = (message.text or "").split()
    if len(parts) == 2:
        try:
            target_id = int(parts[1])
            if add_admin(target_id):
                await message.answer(f"Admin added: ID {target_id}")
            else:
                await message.answer("User is already an admin.")
        except ValueError:
            await message.answer("Usage: Reply to user with /add_admin or /add_admin <user_id>")
        return
    await message.answer("Usage: Reply to user with /add_admin or /add_admin <user_id>")


@router.message(Command("remove_admin"))
async def remove_admin_command(message: Message) -> None:
    if message.from_user.id not in get_admin_ids():
        await message.answer("Only existing admins can remove admins.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Usage: /remove_admin <user_id>")
        return
    try:
        target_id = int(parts[1])
        if target_id == message.from_user.id:
            await message.answer("You cannot remove yourself as admin.")
            return
        if remove_admin(target_id):
            await message.answer(f"Admin removed: ID {target_id}")
        else:
            await message.answer("User is not a dynamic admin.")
    except ValueError:
        await message.answer("Invalid user ID.")


@router.message(Command("list_admins"))
async def list_admins_command(message: Message) -> None:
    if message.from_user.id not in get_admin_ids():
        await message.answer("Only admins can view the admin list.")
        return
    admins = get_admin_ids()
    lines = ["  - " + str(aid) for aid in sorted(admins)]
    admin_list = "\n".join(lines)
    await message.answer("Current admins:\n" + admin_list)


# -- /cancel for all states --

@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("\u2139\ufe0f Nothing to cancel.")
        return
    await state.clear()
    await message.answer("\u274c Cancelled.")
