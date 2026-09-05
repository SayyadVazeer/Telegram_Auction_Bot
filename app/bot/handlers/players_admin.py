import logging
import os
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.types import FSInputFile
from sqlalchemy import func, select

from app.bot.filters.admin import AdminFilter, is_admin
from app.services.admin_service import add_admin, remove_admin, get_admin_ids
from app.database.session import AsyncSessionLocal
from app.database.models.auction import AuctionResult
from app.database.models.team import Team
from app.database.models.player import Player
from app.repositories.team_repository import get_team_by_owner, get_team_by_owner_or_coowner, get_teams_by_tournament, get_team_by_short_code
from app.services.tournament_service import TournamentService
from app.utils.enums import AuctionResultStatus

router = Router()


# -- player_image_change_generator --

GIF_FILE_KEYS = {
    "bid1": "data/bid1.gif",
    "bid2": "data/bid2.gif",
    "bid3": "data/bid3.gif",
    "bid4": "data/bid4.gif",
    "once": "data/once.jpg",
    "twice": "data/twice.jpg",
    "sold": "data/sold.gif",
    "unsold": "data/unsold.gif",
}


@router.message(Command("player_image_change_generator"), AdminFilter())
async def player_image_change_generator(message: Message) -> None:
    """Upload ALL player photos + GIF media to Telegram, save file_ids & unique_ids.

    Usage:
      /player_image_change_generator         -> Upload all players
      /player_image_change_generator --gifs  -> Upload GIF files only
      /player_image_change_generator --all   -> Both players + GIFs
    """
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return

    parts = (message.text or "").split()
    mode = "players"
    if len(parts) > 1:
        flag = parts[1].lower()
        if flag in ("--gifs", "-g"):
            mode = "gifs"
        elif flag in ("--all", "-a"):
            mode = "all"

    import asyncio
    import time

    sent_count = 0
    saved_count = 0
    skipped_count = 0
    failed_count = 0
    from app.bot.handlers.auction import _media_file_ids

    # --- Upload player photos ---
    if mode in ("players", "all"):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Player).order_by(Player.id))
            players = list(result.scalars().all())

        if not players:
            await message.answer("No players found in the database.")
        else:
            await message.answer(f"Starting upload of {len(players)} player photos...")

            batch_count = 0
            for i, player in enumerate(players):
                # Skip if already has telegram_file_id
                if player.telegram_file_id:
                    skipped_count += 1
                    continue
                photo_path = player.telegram_photo_path
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
                        unique_id = sent.photo[-1].file_unique_id
                        async with AsyncSessionLocal() as session:
                            db_player = await session.get(Player, player.id)
                            if db_player:
                                db_player.telegram_file_id = file_id
                                await session.commit()
                                saved_count += 1

                    batch_count += 1
                    # Telegram rate limit: ~30 messages/min. Pause after 25.
                    if batch_count >= 25:
                        await message.answer(f"Pausing 60s to avoid rate limit... ({i+1}/{len(players)} done)")
                        await asyncio.sleep(60)
                        batch_count = 0

                except Exception as e:
                    logging.warning("Failed for %s: %s", player.player_id, e)
                    failed_count += 1

            await message.answer(
                f"Player photos done!\n\n"
                f"Sent: {sent_count}\n"
                f"Saved: {saved_count}\n"
                f"Failed: {failed_count}\n"
                f"Skipped (no local file): {skipped_count}"
            )

    # --- Upload GIF/media files ---
    if mode in ("gifs", "all"):
        await message.answer("Starting GIF/media upload...")
        gif_sent = 0
        gif_saved = 0
        gif_failed = 0

        for key, filepath in GIF_FILE_KEYS.items():
            if not os.path.exists(filepath):
                await message.answer(f"Skipping {key}: {filepath} not found")
                gif_failed += 1
                continue

            try:
                ext = os.path.splitext(filepath)[1].lower()
                if ext in (".jpg", ".jpeg", ".png"):
                    sent = await message.answer_photo(
                        FSInputFile(filepath),
                        caption=f"MEDIA:{key}",
                    )
                    if sent.photo:
                        _media_file_ids[key] = sent.photo[-1].file_id
                        gif_sent += 1
                        gif_saved += 1
                        await message.answer(
                            f"Saved {key}\n"
                            f"File ID: {sent.photo[-1].file_id}\n"
                            f"Unique ID: {sent.photo[-1].file_unique_id}"
                        )
                else:
                    sent = await message.bot.send_animation(
                        message.chat.id,
                        FSInputFile(filepath),
                        caption=f"MEDIA:{key}",
                    )
                    if sent.animation:
                        _media_file_ids[key] = sent.animation.file_id
                        gif_sent += 1
                        gif_saved += 1
                        await message.answer(
                            f"Saved {key}\n"
                            f"File ID: {sent.animation.file_id}\n"
                            f"Unique ID: {sent.animation.file_unique_id}"
                        )
            except Exception as e:
                logging.warning("Failed GIF %s: %s", key, e)
                gif_failed += 1

        await message.answer(
            f"GIF upload done!\n\n"
            f"Sent: {gif_sent}\n"
            f"Saved: {gif_saved}\n"
            f"Failed: {gif_failed}"
        )





# -- swap_player --

# =====================================================
# Admin: Manually sell player to team (unsold or not-yet-auctioned)
# =====================================================

class ManualSold(StatesGroup):
    waiting_for_player_id = State()
    waiting_for_team_code = State()
    waiting_for_confirm = State()


@router.message(Command("manual_sell"), AdminFilter())
async def manual_sell_start(message: Message, state: FSMContext) -> None:
    """Admin manually assigns an unsold or not-yet-auctioned player to a team."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    if message.from_user is None:
        return

    await state.clear()
    await state.set_state(ManualSold.waiting_for_player_id)
    await message.answer("Enter the player ID (e.g. PLY0001):\nUse /cancel to cancel.")


@router.message(ManualSold.waiting_for_player_id)
async def manual_sell_player(message: Message, state: FSMContext) -> None:
    pid = (message.text or "").strip()
    async with AsyncSessionLocal() as session:
        player = await session.scalar(select(Player).where(Player.player_id == pid))
    if not player:
        await message.answer(f"Player {pid} not found. Try again:")
        return
    await state.update_data(player_id=pid, player_db_id=player.id, base_price=float(player.base_price_cr))
    await state.set_state(ManualSold.waiting_for_team_code)
    await message.answer(
        f"Player: {player.name} (Base price: Rs.{player.base_price_cr:.2f} Cr)\n\n"
        "Enter the team short code (e.g. CSK):"
    )


@router.message(ManualSold.waiting_for_team_code)
async def manual_sell_team(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return
        team = await get_team_by_short_code(session, tournament.id, code)
        if not team:
            await message.answer(f"No team with code {code}. Try again:")
            return

        # Calculate remaining purse
        from sqlalchemy import func as sa_func
        total_spent_result = await session.execute(
            select(sa_func.coalesce(sa_func.sum(AuctionResult.final_bid_cr), 0))
            .where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        total_spent = Decimal(str(total_spent_result.scalar() or 0))
        total_spent += Decimal(str(team.purse_adjustment_cr or 0))
        remaining = tournament.purse_cr - total_spent

    data = await state.get_data()
    base_price = data.get('base_price', 0)

    await state.update_data(team_id=team.id, team_name=team.name, team_code=team.short_code, remaining_purse=float(remaining))
    await state.set_state(ManualSold.waiting_for_confirm)
    await message.answer(
        f"Player: {data['player_id']}\n"
        f"Team: {team.name} ({team.short_code})\n"
        f"Amount: Rs.{base_price:.2f} Cr (base price)\n"
        f"Team remaining purse: Rs.{remaining:.2f} Cr\n\n"
        f"Type 'yes' to confirm, or enter a different amount:"
    )


@router.message(ManualSold.waiting_for_confirm)
async def manual_sell_confirm(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()

    if text.lower() == "cancel":
        await state.clear()
        await message.answer("Cancelled.")
        return

    # Check if admin entered a custom amount or confirmed
    if text.lower() == "yes":
        amount = Decimal(str(data.get('base_price', 0)))
    else:
        try:
            amount = Decimal(text)
            if amount <= 0:
                raise ValueError
        except Exception:
            await message.answer("Enter 'yes' for base price, a valid amount, or /cancel:")
            return

    # Check purse
    remaining = Decimal(str(data.get('remaining_purse', 0)))
    if amount > remaining:
        await message.answer(
            f"Insufficient purse! Team has Rs.{remaining:.2f} Cr remaining.\n"
            f"Enter a lower amount or /cancel:"
        )
        return

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        player = await session.get(Player, data['player_db_id'])
        team = await session.get(Team, data['team_id'])

        # Check if already sold
        existing = await session.execute(
            select(AuctionResult).where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.player_id == data['player_db_id'],
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        if existing.scalar_one_or_none():
            await state.clear()
            await message.answer("This player is already sold to another team!")
            return

        # Check max players per team
        team_count_result = await session.execute(
            select(func.count(AuctionResult.id)).where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        team_player_count = int(team_count_result.scalar() or 0)
        if team_player_count >= tournament.max_players_per_team:
            await state.clear()
            await message.answer(
                f"❌ {team.name} already has {team_player_count}/{tournament.max_players_per_team} players (max reached)!"
            )
            return

        # Check overseas limit
        if player.is_overseas:
            team_ovr_result = await session.execute(
                select(func.count(AuctionResult.id))
                .join(Player, Player.id == AuctionResult.player_id)
                .where(
                    AuctionResult.tournament_id == tournament.id,
                    AuctionResult.winning_team_id == team.id,
                    AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                    Player.is_overseas == True,
                )
            )
            team_overseas = int(team_ovr_result.scalar() or 0)
            if team_overseas >= tournament.max_overseas_players:
                await state.clear()
                await message.answer(
                    f"❌ {team.name} already has {team_overseas}/{tournament.max_overseas_players} overseas players (max reached)!"
                )
                return

        # Update existing UNSOLD result or create new one
        result_q = await session.execute(
            select(AuctionResult).where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.player_id == data['player_db_id'],
                AuctionResult.result_status == AuctionResultStatus.UNSOLD.value,
            )
        )
        auction_result = result_q.scalar_one_or_none()

        if auction_result:
            auction_result.result_status = AuctionResultStatus.SOLD.value
            auction_result.winning_team_id = team.id
            auction_result.final_bid_cr = amount
        else:
            auction_result = AuctionResult(
                tournament_id=tournament.id,
                auction_run_id=None,
                auction_player_id=None,
                player_id=data['player_db_id'],
                result_status=AuctionResultStatus.SOLD.value,
                winning_team_id=team.id,
                final_bid_cr=amount,
            )
            session.add(auction_result)

        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Manual sale complete!\n\n"
        f"Player: {player.name}\n"
        f"Team: {team.name} ({team.short_code})\n"
        f"Amount: Rs.{amount:.2f} Cr"
    )


# =====================================================
# Admin: Remove player from team (unsold) with purse restore
# =====================================================

class ManualUnsold(StatesGroup):
    waiting_for_team_code = State()
    waiting_for_player_id = State()
    waiting_for_confirm = State()


@router.message(Command("manual_unsell"), AdminFilter())
async def manual_unsell_start(message: Message, state: FSMContext) -> None:
    """Admin removes a sold player from a team, marks unsold, restores purse."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured for this group.")
            return

        teams = list((await session.execute(
            select(Team).where(Team.tournament_id == tournament.id)
        )).scalars())

        if not teams:
            await message.answer("No teams found.")
            return

    await state.clear()
    await state.set_state(ManualUnsold.waiting_for_team_code)

    team_list = "\n".join(f"{t.short_code} | {t.name}" for t in teams)
    await message.answer(
        f"Select a team:\n\n{team_list}\n\n"
        "Enter the team short code:"
    )


@router.message(ManualUnsold.waiting_for_team_code)
async def manual_unsell_team(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return
        team = await get_team_by_short_code(session, tournament.id, code)
        if not team:
            await message.answer(f"No team with code {code}. Try again:")
            return

        # Get sold players for this team
        from sqlalchemy import func as sa_func
        sold_result = await session.execute(
            select(AuctionResult, Player)
            .join(Player, Player.id == AuctionResult.player_id)
            .where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        sold = list(sold_result.all())

        if not sold:
            await message.answer(f"No sold players in {team.name} ({team.short_code}).")
            return

        # Calculate remaining purse
        total_spent_result = await session.execute(
            select(sa_func.coalesce(sa_func.sum(AuctionResult.final_bid_cr), 0))
            .where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        total_spent = Decimal(str(total_spent_result.scalar() or 0))
        total_spent += Decimal(str(team.purse_adjustment_cr or 0))
        remaining = tournament.purse_cr - total_spent

    await state.update_data(
        team_id=team.id, team_name=team.name, team_code=team.short_code,
        remaining_purse=float(remaining)
    )
    await state.set_state(ManualUnsold.waiting_for_player_id)

    player_list = "\n".join(
        f"{p.player_id} | {p.name} | Rs.{Decimal(str(r.final_bid_cr)):.2f} Cr"
        for r, p in sold[:20]
    )
    await message.answer(
        f"Sold players in {team.name} ({team.short_code}):\n\n"
        f"{player_list}\n\n"
        f"Team purse: Rs.{remaining:.2f} Cr (after these purchases)\n\n"
        "Enter the player ID to unsell:"
    )


@router.message(ManualUnsold.waiting_for_player_id)
async def manual_unsell_player(message: Message, state: FSMContext) -> None:
    pid = (message.text or "").strip()
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuctionResult, Player)
            .join(Player, Player.id == AuctionResult.player_id)
            .where(
                Player.player_id == pid,
                AuctionResult.tournament_id.in_(
                    select(Team.tournament_id).where(Team.id == data['team_id'])
                ),
                AuctionResult.winning_team_id == data['team_id'],
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        row = result.first()

    if not row:
        await message.answer(f"No sold player {pid} in this team. Try again:")
        return

    auction_result, player = row
    await state.update_data(
        result_id=auction_result.id,
        player_id=pid,
        player_name=player.name,
        sale_amount=float(auction_result.final_bid_cr),
    )
    await state.set_state(ManualUnsold.waiting_for_confirm)
    await message.answer(
        f"Remove {player.name} ({pid}) from {data['team_name']}?\n\n"
        f"Sale amount: Rs.{Decimal(str(auction_result.final_bid_cr)):.2f} Cr\n"
        f"This will be added back to the team's remaining purse.\n\n"
        "Type 'yes' to confirm:"
    )


@router.message(ManualUnsold.waiting_for_confirm)
async def manual_unsell_confirm(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip().lower() != "yes":
        await state.clear()
        await message.answer("Cancelled.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        result = await session.get(AuctionResult, data['result_id'])
        if result:
            result.result_status = AuctionResultStatus.UNSOLD.value
            result.winning_team_id = None
            result.final_bid_cr = None
            await session.commit()

    restored = Decimal(str(data.get('sale_amount', 0)))
    await state.clear()
    await message.answer(
        f"✅ Removed {data['player_name']} ({data['player_id']}) from {data['team_name']}.\n"
        f"Marked as unsold. Rs.{restored:.2f} Cr added back to team purse."
    )




# =====================================================
# Player Trade with approval from both owners
# =====================================================

class TradePlayer(StatesGroup):
    waiting_for_from_player = State()
    waiting_for_to_team = State()
    waiting_for_to_player = State()
    waiting_for_from_owner_confirm = State()
    waiting_for_to_owner_confirm = State()


trade_states = TradePlayer

# Global trade store (in-memory, per-process)
_pending_trades: dict[int, dict] = {}  # owner_telegram_id -> trade data


def _store_pending_trade(to_owner_id: int, trade_data: dict) -> None:
    """Store a pending trade for the receiving owner."""
    _pending_trades[to_owner_id] = trade_data


def _get_pending_trade(owner_id: int) -> dict | None:
    """Get and remove a pending trade for this owner."""
    return _pending_trades.pop(owner_id, None)




# ── Trade toggle commands ──────────────────────────────

@router.message(Command("trade_on"), AdminFilter())
async def trade_on(message: Message) -> None:
    """Enable the trade feature."""
    from app.services.admin_service import set_trade_enabled
    set_trade_enabled(True)
    await message.answer("Player trade is now ENABLED.")


@router.message(Command("trade_off"), AdminFilter())
async def trade_off(message: Message) -> None:
    """Disable the trade feature."""
    from app.services.admin_service import set_trade_enabled
    set_trade_enabled(False)
    await message.answer("Player trade is now DISABLED.")


@router.message(Command("trade_player"))
async def trade_player_start(message: Message, state: FSMContext) -> None:
    """Initiate a player trade between two teams."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    if message.from_user is None:
        return

    from app.services.admin_service import is_trade_enabled
    if not is_trade_enabled():
        await message.answer("Player trade is currently disabled. Admin can enable it with /trade_on.")
        return

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament is configured for this group.")
            return
        team = await get_team_by_owner_or_coowner(session, tournament.id, message.from_user.id)
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
        await message.answer("No players to trade.")
        return
    await state.clear()
    await state.update_data(
        from_team_id=team.id,
        from_team_name=team.name,
        from_team_code=team.short_code,
        from_owner_id=message.from_user.id,
        from_owner_username=message.from_user.username or "",
        players=players,
        chat_id=message.chat.id,
    )
    from app.bot.keyboards.home import trade_player_keyboard
    await state.set_state(trade_states.waiting_for_from_player)
    await message.answer(
        f"Your team: {team.name} ({team.short_code})\n\n"
        "Select a player to trade away:",
        reply_markup=trade_player_keyboard(players),
    )


@router.callback_query(F.data.startswith("trade:player:"), trade_states.waiting_for_from_player)
async def trade_from_player_callback(callback: CallbackQuery, state: FSMContext) -> None:
    pid = callback.data.split(":")[-1]
    data = await state.get_data()
    players = data.get("players", [])
    found = None
    for r, p in players:
        if p.player_id == pid:
            found = (r, p)
            break
    if not found:
        await callback.answer("Player not found.", show_alert=True)
        return
    r, p = found
    await state.update_data(
        from_player_id=p.id,
        from_player_name=p.name,
        from_player_pid=p.player_id,
        from_player_bid=float(r.final_bid_cr),
    )
    await callback.answer(f"Selected: {p.name}")
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        teams = await get_teams_by_tournament(session, tournament.id) if tournament else []
        other_teams = [t for t in teams if t.id != data['from_team_id']]
    if not other_teams:
        await state.clear()
        await callback.message.answer("No other teams to trade with.")
        return
    await state.update_data(other_teams=[(t.id, t.name, t.short_code, t.owner_telegram_id or 0, t.owner_username or "") for t in other_teams])
    from app.bot.keyboards.home import trade_team_keyboard
    await state.set_state(trade_states.waiting_for_to_team)
    await callback.message.answer(
        f"Trading: {p.name}\n\n"
        "Select a team to trade with:",
        reply_markup=trade_team_keyboard(other_teams),
    )


@router.callback_query(F.data.startswith("trade:team:"), trade_states.waiting_for_to_team)
async def trade_to_team_callback(callback: CallbackQuery, state: FSMContext) -> None:
    code = callback.data.split(":")[-1]
    data = await state.get_data()
    other_teams = data.get("other_teams", [])
    found_team = None
    for tid, tname, tcode, towner_id, towner_name in other_teams:
        if tcode == code:
            found_team = (tid, tname, tcode, towner_id, towner_name)
            break
    if not found_team:
        await callback.answer("Team not found.", show_alert=True)
        return
    await callback.answer(f"Selected: {code}")
    tid, tname, tcode, towner_id, towner_name = found_team
    await state.update_data(
        to_team_id=tid, to_team_name=tname, to_team_code=tcode,
        to_owner_id=towner_id, to_owner_username=towner_name,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuctionResult, Player)
            .join(Player, Player.id == AuctionResult.player_id)
            .where(
                AuctionResult.winning_team_id == tid,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        to_players = [(r, p) for r, p in result.all()]
    if not to_players:
        await callback.message.answer(f"{tname} has no players to trade.")
        await state.clear()
        return
    await state.update_data(to_players=to_players)
    from app.bot.keyboards.home import trade_player_keyboard
    await state.set_state(trade_states.waiting_for_to_player)
    await callback.message.answer(
        f"{tname} ({tcode}) players:\n\n"
        "Select a player to receive:",
        reply_markup=trade_player_keyboard(to_players),
    )


@router.callback_query(F.data.startswith("trade:player:"), trade_states.waiting_for_to_player)
async def trade_to_player_callback(callback: CallbackQuery, state: FSMContext) -> None:
    pid = callback.data.split(":")[-1]
    data = await state.get_data()
    to_players = data.get("to_players", [])
    found = None
    for r, p in to_players:
        if p.player_id == pid:
            found = (r, p)
            break
    if not found:
        await callback.answer("Player not found.", show_alert=True)
        return
    r, p = found
    await state.update_data(
        to_player_id=p.id,
        to_player_name=p.name,
        to_player_pid=p.player_id,
        to_player_bid=float(r.final_bid_cr),
    )
    await callback.answer(f"Selected: {p.name}")
    from_player = data.get('from_player_name', '?')
    from app.bot.keyboards.home import trade_confirm_keyboard
    await state.set_state(trade_states.waiting_for_from_owner_confirm)
    await callback.message.answer(
        f"Trade proposal:\n\n"
        f"{data['from_team_name']} ({data['from_team_code']}) sends: {from_player}\n"
        f"{data['to_team_name']} ({data['to_team_code']}) sends: {p.name}\n\n"
        "Confirm trade?",
        reply_markup=trade_confirm_keyboard(),
    )


_trade_counter = 0


@router.callback_query(F.data == "trade:confirm", trade_states.waiting_for_from_owner_confirm)
async def trade_from_owner_confirm_callback(callback: CallbackQuery, state: FSMContext) -> None:
    global _trade_counter
    await callback.answer("Trade proposal sent!")
    data = await state.get_data()
    to_owner_id = data.get('to_owner_id')
    if not to_owner_id:
        await callback.message.answer("Could not find the other team owner.")
        return

    _trade_counter += 1
    trade_data = data.copy()
    trade_data["chat_id"] = callback.message.chat.id
    trade_data["thread_id"] = getattr(callback.message, "message_thread_id", None)
    trade_data["trade_id"] = _trade_counter
    _store_pending_trade(to_owner_id, trade_data)

    from_price = Decimal(str(data.get('from_player_bid', 0)))
    to_price = Decimal(str(data.get('to_player_bid', 0)))
    diff = float(from_price - to_price)
    if diff > 0:
        purse_text = f"\n\nPurse: {data['to_team_name']} pays Rs.{diff:.2f} Cr to {data['from_team_name']}"
    elif diff < 0:
        purse_text = f"\n\nPurse: {data['from_team_name']} pays Rs.{abs(diff):.2f} Cr to {data['to_team_name']}"
    else:
        purse_text = "\n\nPurse: Equal value - no change"

    from app.bot.keyboards.home import trade_action_keyboard
    await callback.message.answer(
        f"📥 Trade Proposal\n\n"
        f"{data['from_team_name']} ({data['from_team_code']}) sends:\n"
        f"  {data['from_player_name']} (Rs.{from_price:.2f} Cr)\n\n"
        f"{data['to_team_name']} ({data['to_team_code']}) sends:\n"
        f"  {data['to_player_name']} (Rs.{to_price:.2f} Cr)"
        f"{purse_text}\n\n"
        f"To owner: @{data.get('to_owner_username', 'N/A')}\n"
        "Accept or reject the trade:",
        reply_markup=trade_action_keyboard(),
    )
    await state.clear()


async def _send_admin_approval(send_fn, trade_data: dict) -> None:
    """Post the accepted trade as a message requiring admin approval."""
    from app.bot.keyboards.home import trade_admin_keyboard

    from_price = Decimal(str(trade_data.get('from_player_bid', 0)))
    to_price = Decimal(str(trade_data.get('to_player_bid', 0)))
    diff = float(from_price - to_price)
    if diff > 0:
        purse_text = f"\n\nPurse: {trade_data['to_team_name']} pays Rs.{diff:.2f} Cr to {trade_data['from_team_name']}"
    elif diff < 0:
        purse_text = f"\n\nPurse: {trade_data['from_team_name']} pays Rs.{abs(diff):.2f} Cr to {trade_data['to_team_name']}"
    else:
        purse_text = "\n\nPurse: Equal value - no change"

    await send_fn(
        f"⏰ Trade Pending Admin Approval\n\n"
        f"{trade_data['from_team_name']} ({trade_data['from_team_code']}) sends:\n"
        f"  {trade_data['from_player_name']} (Rs.{from_price:.2f} Cr)\n\n"
        f"{trade_data['to_team_name']} ({trade_data['to_team_code']}) sends:\n"
        f"  {trade_data['to_player_name']} (Rs.{to_price:.2f} Cr)"
        f"{purse_text}\n\n"
        f"Accepted by: @{trade_data.get('accepted_by_username', 'N/A')}\n\n"
        "Admin: Approve or reject this trade:",
        reply_markup=trade_admin_keyboard(),
    )


@router.callback_query(F.data == "trade:accept")
async def trade_accept_button(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    data = _get_pending_trade(callback.from_user.id)
    if not data:
        await callback.answer("No active trade to accept.", show_alert=True)
        return
    if callback.from_user.id != data.get("to_owner_id"):
        await callback.answer("Only the receiving team owner can accept.", show_alert=True)
        return
    await callback.answer("Trade accepted! Sending to admin for approval...")

    # Store for admin approval
    trade_data = data.copy()
    trade_data["accepted_by"] = callback.from_user.id
    trade_data["accepted_by_username"] = callback.from_user.username or ""
    _store_pending_trade("admin_pending", trade_data)

    # Remove owner buttons
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _send_admin_approval(callback.message.answer, trade_data)


@router.callback_query(F.data == "trade:reject")
async def trade_reject_button(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    data = _get_pending_trade(callback.from_user.id)
    if not data:
        await callback.answer("No active trade to reject.", show_alert=True)
        return
    if callback.from_user.id != data.get("to_owner_id"):
        await callback.answer("Only the receiving team owner can reject.", show_alert=True)
        return
    await callback.answer("Trade rejected.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        f"❌ Trade rejected by {data.get('to_team_name', 'team')} owner."
    )
    # Notify the initiating owner via DM
    from_owner_id = data.get("from_owner_id")
    if from_owner_id:
        try:
            await callback.message.bot.send_message(
                from_owner_id,
                "❌ Your trade proposal was rejected.",
            )
        except Exception:
            pass




@router.callback_query(F.data == "trade:admin_approve")
async def trade_admin_approve_button(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Only admins can approve trades.", show_alert=True)
        return
    data = _get_pending_trade("admin_pending")
    if not data:
        await callback.answer("No trade pending approval.", show_alert=True)
        return
    await callback.answer("Trade approved! Executing...")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _execute_trade(callback, data)


@router.callback_query(F.data == "trade:admin_reject")
async def trade_admin_reject_button(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    if not is_admin(callback.from_user.id):
        await callback.answer("Only admins can reject trades.", show_alert=True)
        return
    _get_pending_trade("admin_pending")  # Remove from queue
    await callback.answer("Trade rejected by admin.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("❌ Trade rejected by admin.")


@router.callback_query(F.data == "trade:cancel")
async def trade_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:

    await state.clear()

    await callback.answer("Trade cancelled.")

    await callback.message.answer("Trade cancelled.")



async def _execute_trade(context, data: dict) -> None:
    """Execute a trade from button callback or command. Works in group chat."""
    if hasattr(context, "message") and hasattr(context, "from_user"):
        chat_id = context.message.chat.id
        send_fn = context.message.answer
        bot = context.message.bot
        user_id = context.from_user.id if context.from_user else 0
    else:
        chat_id = context.chat.id
        send_fn = context.answer
        bot = context.bot
        user_id = context.from_user.id if context.from_user else 0

    from_price = Decimal(str(data.get("from_player_bid", 0)))
    to_price = Decimal(str(data.get("to_player_bid", 0)))
    diff = float(from_price - to_price)

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(chat_id)
        if not tournament:
            await send_fn("No tournament found.")
            return

        from_team = await session.get(Team, data["from_team_id"])
        to_team = await session.get(Team, data["to_team_id"])

        if not from_team or not to_team:
            await send_fn("Team not found.")
            return

        from_result_q = await session.execute(
            select(AuctionResult).where(
                AuctionResult.winning_team_id == from_team.id,
                AuctionResult.player_id == data["from_player_id"],
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        from_result = from_result_q.scalar_one_or_none()

        to_result_q = await session.execute(
            select(AuctionResult).where(
                AuctionResult.winning_team_id == to_team.id,
                AuctionResult.player_id == data["to_player_id"],
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        to_result = to_result_q.scalar_one_or_none()

        if not from_result or not to_result:
            await send_fn("Player trade records not found.")
            return

        # Validate trade caps
        from_player_obj = await session.get(Player, data["from_player_id"])
        to_player_obj = await session.get(Player, data["to_player_id"])
        trade_error = await _validate_trade(session, tournament, from_team, to_team, from_player_obj, to_player_obj)
        if trade_error:
            await send_fn(f"❌ {trade_error}")
            return

        if diff > 0:
            spent = await _get_team_spent(session, tournament.id, to_team.id)
            remaining = Decimal(str(tournament.purse_cr)) - spent
            if Decimal(str(diff)) > remaining:
                await send_fn(
                    f"❌ Trade rejected. {to_team.name} has only Rs.{remaining:.2f} Cr remaining. "
                    f"Needs Rs.{diff:.2f} Cr for this trade."
                )
                return
        elif diff < 0:
            spent = await _get_team_spent(session, tournament.id, from_team.id)
            remaining = Decimal(str(tournament.purse_cr)) - spent
            if Decimal(str(abs(diff))) > remaining:
                await send_fn(
                    f"❌ Trade rejected. {from_team.name} has only Rs.{remaining:.2f} Cr remaining. "
                    f"Needs Rs.{abs(diff):.2f} Cr for this trade."
                )
                return

        # Apply real purse settlement for the value difference
        if diff > 0:
            # to_team pays Rs.diff to from_team
            to_team.purse_adjustment_cr = Decimal(str(to_team.purse_adjustment_cr or 0)) + Decimal(str(diff))
            from_team.purse_adjustment_cr = Decimal(str(from_team.purse_adjustment_cr or 0)) - Decimal(str(diff))
        elif diff < 0:
            # from_team pays Rs.abs(diff) to to_team
            from_team.purse_adjustment_cr = Decimal(str(from_team.purse_adjustment_cr or 0)) + Decimal(str(abs(diff)))
            to_team.purse_adjustment_cr = Decimal(str(to_team.purse_adjustment_cr or 0)) - Decimal(str(abs(diff)))

        from_result.winning_team_id = to_team.id
        to_result.winning_team_id = from_team.id
        await session.commit()

    if diff > 0:
        settlement = f"\n\nPurse: {to_team.name} pays Rs.{diff:.2f} Cr to {from_team.name}"
    elif diff < 0:
        settlement = f"\n\nPurse: {from_team.name} pays Rs.{abs(diff):.2f} Cr to {to_team.name}"
    else:
        settlement = "\n\nPurse: Equal value - no change"

    # Remove inline buttons from the proposal message
    try:
        if hasattr(context, "message"):
            await context.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await send_fn(
        f"✅ Trade complete!\n\n"
        f"{from_team.name} ({from_team.short_code}) received: {data['to_player_name']} (Rs.{to_price:.2f} Cr)\n"
        f"{to_team.name} ({to_team.short_code}) received: {data['from_player_name']} (Rs.{from_price:.2f} Cr)"
        f"{settlement}"
    )

    # Show updated team rosters in the group
    try:
        async with AsyncSessionLocal() as session:
            thread_kw = (
                {"message_thread_id": data.get("thread_id")}
                if data.get("thread_id")
                else {}
            )
            for tid in [(from_team.id, from_team.name), (to_team.id, to_team.name)]:
                tm = await session.get(Team, tid[0])
                if not tm:
                    continue
                results_q = await session.execute(
                    select(AuctionResult, Player)
                    .join(Player, Player.id == AuctionResult.player_id)
                    .where(
                        AuctionResult.winning_team_id == tid[0],
                        AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                    )
                    .order_by(AuctionResult.final_bid_cr.desc())
                )
                roster = list(results_q.all())
                spent = sum(Decimal(str(r.final_bid_cr)) for r, _ in roster)
                spent += Decimal(str(tm.purse_adjustment_cr or 0))
                overseas = sum(1 for _, p in roster if p.is_overseas)
                players_text = "\n".join(
                    f"• {p.name} {'✈️' if p.is_overseas else ''} -- Rs.{r.final_bid_cr:.2f} Cr"
                    for r, p in roster
                ) or "No players"
                owner_display = (
                    f"@{tm.owner_username}" if tm.owner_username
                    else (str(tm.owner_telegram_id) if tm.owner_telegram_id else "N/A")
                )
                await bot.send_message(
                    chat_id,
                    f"📋 {tm.name} ({tm.short_code})\n"
                    f"Owner: {owner_display}\n"
                    f"Purse: Rs.{Decimal(str(tournament.purse_cr)) - spent:.2f} Cr remaining\n"
                    f"Players: {len(roster)}/{tournament.max_players_per_team} | Overseas: {overseas}/{tournament.max_overseas_players}\n\n"
                    f"Roster:\n{players_text}",
                    **thread_kw,
                )
    except Exception:
        pass

    # Notify the other owner via DM if possible
    from_owner_id = data.get("from_owner_id")
    if from_owner_id and from_owner_id != user_id:
        try:
            await bot.send_message(
                from_owner_id,
                f"✅ Trade accepted!\n\n"
                f"You received: {data['to_player_name']} (Rs.{to_price:.2f} Cr)\n"
                f"They received: {data['from_player_name']} (Rs.{from_price:.2f} Cr)"
                f"{settlement}"
            )
        except Exception:
            pass


@router.message(Command("accept_trade"))
async def accept_trade(message: Message, state: FSMContext) -> None:
    """Accept a pending trade via /accept_trade command.

    Same flow as the accept button: routes to admin for approval instead of
    executing immediately, so both paths enforce the same authorization.
    """
    if message.from_user is None:
        return
    data = _get_pending_trade(message.from_user.id)
    if not data:
        await message.answer("No active trade to accept.")
        return
    if message.from_user.id != data.get("to_owner_id"):
        await message.answer("Only the receiving team owner can accept this trade.")
        return

    trade_data = data.copy()
    trade_data["accepted_by"] = message.from_user.id
    trade_data["accepted_by_username"] = message.from_user.username or ""
    _store_pending_trade("admin_pending", trade_data)

    await message.answer("✅ Trade accepted! Sending to admin for approval...")
    await _send_admin_approval(message.answer, trade_data)




# =====================================================
# Admin: Delete team and change owner
# =====================================================

class TeamAdmin(StatesGroup):
    waiting_for_delete_code = State()
    waiting_for_delete_confirm = State()
    waiting_for_remove_owner_code = State()
    waiting_for_remove_owner_confirm = State()


@router.message(Command("delete_team"), AdminFilter())
async def delete_team_start(message: Message, state: FSMContext) -> None:
    """Admin deletes a team and removes all its player associations."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return
        teams = list((await session.execute(
            select(Team).where(Team.tournament_id == tournament.id)
        )).scalars())
        if not teams:
            await message.answer("No teams found.")
            return
    await state.clear()
    team_list = "\n".join(f"{t.short_code} | {t.name}" for t in teams)
    await state.set_state(TeamAdmin.waiting_for_delete_code)
    await message.answer(
        f"Teams:\n\n{team_list}\n\n"
        "Enter the team short code to delete:"
    )


@router.message(TeamAdmin.waiting_for_delete_code)
async def delete_team_code(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        team = await get_team_by_short_code(session, tournament.id, code) if tournament else None
    if not team:
        await message.answer(f"No team with code {code}. Try again:")
        return
    await state.update_data(delete_team_id=team.id, delete_team_name=team.name, delete_team_code=team.short_code)
    await state.set_state(TeamAdmin.waiting_for_delete_confirm)
    await message.answer(
        f"Delete {team.name} ({team.short_code})?\n\n"
        "All player associations for this team will be removed.\n"
        "Type 'yes' to confirm:"
    )


@router.message(TeamAdmin.waiting_for_delete_confirm)
async def delete_team_confirm(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip().lower() != "yes":
        await state.clear()
        await message.answer("Deletion cancelled.")
        return
    data = await state.get_data()
    deleted_owner_id = None
    deleted_coowner_id = None
    deleted_code = data["delete_team_code"]
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        # Remove all auction results for this team
        from sqlalchemy import delete as sql_delete
        await session.execute(sql_delete(AuctionResult).where(
            AuctionResult.tournament_id == tournament.id,
            AuctionResult.winning_team_id == data["delete_team_id"],
        ))
        # Delete the team
        team = await session.get(Team, data["delete_team_id"])
        if team:
            deleted_owner_id = team.owner_telegram_id
            deleted_coowner_id = team.co_owner_telegram_id
            await session.delete(team)
        await session.commit()
    # Clear group tags for the deleted team's owner and co-owner (best-effort)
    from app.services.group_tags import clear_group_tag, co_owner_title, owner_title
    if deleted_owner_id:
        await clear_group_tag(message.bot, message.chat.id, deleted_owner_id, owner_title(deleted_code))
    if deleted_coowner_id:
        await clear_group_tag(message.bot, message.chat.id, deleted_coowner_id, co_owner_title(deleted_code))
    await state.clear()
    await message.answer(f"✅ Deleted team {data['delete_team_name']} ({data['delete_team_code']}).")


@router.message(Command("remove_owner"), AdminFilter())
async def remove_owner_start(message: Message, state: FSMContext) -> None:
    """Admin removes owner and co-owner from a team."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("⚠️ Usage:\n/remove_owner CSK")
        return
    code = parts[1].strip().upper()
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return
        team = await get_team_by_short_code(session, tournament.id, code)
    if not team:
        await message.answer(f"❌ No team with short code {code}.")
        return
    await state.clear()
    await state.update_data(remove_owner_team_id=team.id, remove_owner_team_name=team.name, remove_owner_team_code=team.short_code)
    await state.set_state(TeamAdmin.waiting_for_remove_owner_confirm)
    owner_display = f"@{team.owner_username}" if team.owner_username else (str(team.owner_telegram_id) if team.owner_telegram_id else "None")
    coowner_display = f"@{team.co_owner_username}" if team.co_owner_username else (str(team.co_owner_telegram_id) if team.co_owner_telegram_id else "None")
    await message.answer(
        f"⚠️ Remove owner from {team.name} ({team.short_code})?\n\n"
        f"Current owner: {owner_display}\n"
        f"Current co-owner: {coowner_display}\n\n"
        "This will clear all owner data. You can reassign later with /assign_owner.\n\n"
        "Type 'yes' to confirm:"
    )


@router.message(TeamAdmin.waiting_for_remove_owner_confirm)
async def remove_owner_confirm(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip().lower() != "yes":
        await state.clear()
        await message.answer("Cancelled.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        team = await session.get(Team, data["remove_owner_team_id"])
        if not team:
            await message.answer("Team not found.")
            await state.clear()
            return
        removed_owner_id = team.owner_telegram_id
        removed_coowner_id = team.co_owner_telegram_id
        team_code = team.short_code
        team.owner_telegram_id = None
        team.owner_username = None
        team.co_owner_telegram_id = None
        team.co_owner_username = None
        await session.commit()
    # Clear group tags for the removed owner and co-owner (best-effort)
    from app.services.group_tags import clear_group_tag, co_owner_title, owner_title
    if removed_owner_id:
        await clear_group_tag(message.bot, message.chat.id, removed_owner_id, owner_title(team_code))
    if removed_coowner_id:
        await clear_group_tag(message.bot, message.chat.id, removed_coowner_id, co_owner_title(team_code))
    await state.clear()
    await message.answer(
        f"✅ Owner removed from {team.name} ({team.short_code}).\n\n"
        "Use /assign_owner to assign a new owner."
    )





# =====================================================
# Admin: Edit team, Add/Remove co-owner
# =====================================================

class EditTeam(StatesGroup):
    waiting_for_team_code = State()
    waiting_for_field = State()
    waiting_for_value = State()


@router.message(Command("edit_team"), AdminFilter())
async def edit_team_start(message: Message, state: FSMContext) -> None:
    """Admin edits team details."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return
        teams = list((await session.execute(
            select(Team).where(Team.tournament_id == tournament.id)
        )).scalars())
        if not teams:
            await message.answer("No teams found.")
            return
    await state.clear()
    team_list = "\n".join(f"{t.short_code} | {t.name}" for t in teams)
    await state.set_state(EditTeam.waiting_for_team_code)
    await message.answer(
        f"Teams:\n\n{team_list}\n\n"
        "Enter the team short code to edit:"
    )


@router.message(EditTeam.waiting_for_team_code)
async def edit_team_code(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        team = await get_team_by_short_code(session, tournament.id, code) if tournament else None
    if not team:
        await message.answer(f"No team with code {code}. Try again:")
        return
    from app.bot.keyboards.home import InlineKeyboardMarkup, InlineKeyboardButton
    await state.update_data(edit_team_id=team.id, edit_team_name=team.name, edit_team_code=team.short_code)
    await state.set_state(EditTeam.waiting_for_field)
    await message.answer(
        f"Editing: {team.name} ({team.short_code})\n"
        f"Owner: @{team.owner_username or 'N/A'}\n"
        f"Co-owner: @{team.co_owner_username or 'N/A'}\n\n"
        "Select field to edit:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Name", callback_data="editteam:name")],
            [InlineKeyboardButton(text="🏷️ Short Code", callback_data="editteam:code")],
            [InlineKeyboardButton(text="🚫 Cancel", callback_data="editteam:cancel")],
        ])
    )


@router.callback_query(F.data.startswith("editteam:"), EditTeam.waiting_for_field)
async def edit_team_field_callback(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":")[-1]
    if field == "cancel":
        await state.clear()
        await callback.answer("Cancelled.")
        await callback.message.answer("Edit cancelled.")
        return
    await state.update_data(edit_field=field)
    await state.set_state(EditTeam.waiting_for_value)
    field_name = "team name" if field == "name" else "short code"
    await callback.message.answer(f"Enter the new {field_name}:")


@router.message(EditTeam.waiting_for_value)
async def edit_team_value(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    data = await state.get_data()
    field = data.get("edit_field")
    async with AsyncSessionLocal() as session:
        team = await session.get(Team, data["edit_team_id"])
        if team:
            if field == "name":
                team.name = value
            elif field == "code":
                team.short_code = value.upper()
            await session.commit()
            await message.answer(f"✅ Updated {field} to {value} for {team.name}.")
        else:
            await message.answer("Team not found.")
    await state.clear()


class CoOwner(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_confirm = State()


@router.message(Command("add_coowner"))
async def add_coowner_start(message: Message, state: FSMContext) -> None:
    """Team owner or admin adds a co-owner to a team.
    
    Usage:
      /add_coowner TTT        -> then reply to person's message
      Reply to person + /add_coowner TTT  -> one-step flow
    """
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    if message.from_user is None:
        return

    await state.clear()
    parts = (message.text or "").strip().split()
    user_is_admin = is_admin(message.from_user.id)

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured for this group.")
            return

        # Determine team
        team = None
        if len(parts) > 1:
            code = parts[1].upper()
            team = await get_team_by_short_code(session, tournament.id, code)
            if not team:
                await message.answer(f"No team with code {code}.")
                return
            if team.owner_telegram_id != message.from_user.id and not user_is_admin:
                await message.answer("Only the team owner or an admin can add a co-owner.")
                return
        else:
            team = await get_team_by_owner(session, tournament.id, message.from_user.id)
            if not team:
                if user_is_admin:
                    teams = list((await session.execute(
                        select(Team).where(Team.tournament_id == tournament.id)
                    )).scalars())
                    if not teams:
                        await message.answer("No teams found.")
                        return
                    team_list = "\n".join(f"{t.short_code} | {t.name}" for t in teams)
                    await state.set_state(CoOwner.waiting_for_user_id)
                    await state.update_data(coowner_team_id=None, pick_team=True, teams=[(t.id, t.name, t.short_code) for t in teams])
                    await message.answer(
                        f"You are an admin. Select a team:\n\n{team_list}\n\n"
                        "Enter the team short code:"
                    )
                    return
                await message.answer("You are not registered as a team owner.")
                return

    # Check if this message IS a reply to someone (one-step flow)
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        if target.is_bot:
            await message.answer("Cannot assign a bot as co-owner.")
            return
        username_display = f"@{target.username}" if target.username else target.full_name
        await state.update_data(
            coowner_team_id=team.id, coowner_team_name=team.name, coowner_team_code=team.short_code,
            coowner_user_id=target.id, coowner_username=target.username or "",
        )
        await state.set_state(CoOwner.waiting_for_confirm)
        await message.answer(
            f"Add {username_display} as co-owner of {team.name} ({team.short_code})?\n\n"
            "Type 'yes' to confirm:"
        )
        return

    # Not a reply — ask them to reply
    await state.update_data(coowner_team_id=team.id, coowner_team_name=team.name, coowner_team_code=team.short_code)
    await state.set_state(CoOwner.waiting_for_user_id)
    await message.answer(
        f"Team: {team.name} ({team.short_code})\n"
        f"Current co-owner: @{team.co_owner_username or 'None'}\n\n"
        "👇 Reply to a message from the person you want as co-owner:\n"
        "(Drag their message and type /add_coowner)",
    )


@router.message(CoOwner.waiting_for_user_id)
async def add_coowner_user_id(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = (message.text or "").strip()

    # Admin picking team first
    if data.get("pick_team"):
        code = text.upper()
        teams = data.get("teams", [])
        found = None
        for tid, tname, tcode in teams:
            if tcode == code:
                found = (tid, tname, tcode)
                break
        if not found:
            await message.answer(f"No team with code {code}. Try again:")
            return
        await state.update_data(coowner_team_id=found[0], coowner_team_name=found[1], coowner_team_code=found[2], pick_team=False)
        await message.answer(
            f"Team: {found[1]} ({found[2]})\n\n"
            "👇 Reply to a message from the person you want as co-owner:\n"
            "Use /cancel to cancel."
        )
        return

    if text.lower() == "cancel":
        await state.clear()
        await message.answer("Cancelled.")
        return

    # Check if the user replied to someone's message
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer(
            "❌ Please reply to a message from the person you want as co-owner.\n"
            "(Drag their message and send this command as a reply)"
        )
        return

    target_user = message.reply_to_message.from_user
    if target_user.is_bot:
        await message.answer("Cannot assign a bot as co-owner.")
        return

    user_id = target_user.id
    username_display = f"@{target_user.username}" if target_user.username else target_user.full_name

    await state.update_data(coowner_user_id=user_id, coowner_username=target_user.username or "")
    await state.set_state(CoOwner.waiting_for_confirm)
    await message.answer(
        f"Add {username_display} (ID: {user_id}) as co-owner of {data['coowner_team_name']} ({data['coowner_team_code']})?\n\n"
        "Type 'yes' to confirm:"
    )


@router.message(CoOwner.waiting_for_confirm)
async def add_coowner_confirm(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    if text != "yes":
        await state.clear()
        await message.answer("Cancelled.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        team = await session.get(Team, data["coowner_team_id"])
        if not team:
            await message.answer("Team not found.")
            await state.clear()
            return

        # Check if user is already an owner of another team
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if tournament:
            owner_result = await session.execute(
                select(Team).where(
                    Team.owner_telegram_id == data["coowner_user_id"],
                    Team.tournament_id == tournament.id,
                )
            )
            existing_owner = owner_result.scalar_one_or_none()
            if existing_owner and existing_owner.id != team.id:
                await state.clear()
                await message.answer(
                    f"❌ This user is already the owner of {existing_owner.name} ({existing_owner.short_code}).\n"
                    "A person cannot be owner of one team and co-owner of another."
                )
                return

            # Check if user is already a co-owner of another team
            coowner_result = await session.execute(
                select(Team).where(
                    Team.co_owner_telegram_id == data["coowner_user_id"],
                    Team.tournament_id == tournament.id,
                )
            )
            existing_coowner = coowner_result.scalar_one_or_none()
            if existing_coowner and existing_coowner.id != team.id:
                await state.clear()
                await message.answer(
                    f"❌ This user is already a co-owner of {existing_coowner.name} ({existing_coowner.short_code}).\n"
                    "A person can only be co-owner of one team."
                )
                return

        team.co_owner_telegram_id = data["coowner_user_id"]
        team.co_owner_username = data.get("coowner_username", None)
        await session.commit()
    # Tag the new co-owner in the group (best-effort)
    from app.services.group_tags import co_owner_title, set_group_tag
    await set_group_tag(
        message.bot, message.chat.id, data["coowner_user_id"],
        co_owner_title(data["coowner_team_code"]),
    )
    await state.clear()
    username_display = f"@{data.get('coowner_username', '')}" if data.get('coowner_username') else str(data['coowner_user_id'])
    await message.answer(
        f"✅ Co-owner added to {data['coowner_team_name']} ({data['coowner_team_code']})\n"
        f"Co-owner: {username_display}"
    )


@router.message(Command("remove_coowner"))
async def remove_coowner(message: Message, state: FSMContext) -> None:
    """Simple one-shot: /delete_coowner TTT or /delete_coowner (own team)."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    if message.from_user is None:
        return

    await state.clear()
    parts = (message.text or "").strip().split()
    user_is_admin = is_admin(message.from_user.id)

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured for this group.")
            return

        team = None
        if len(parts) > 1:
            code = parts[1].upper()
            team = await get_team_by_short_code(session, tournament.id, code)
            if not team:
                await message.answer(f"❌ No team with code {code}.")
                return
            if team.owner_telegram_id != message.from_user.id and not user_is_admin:
                await message.answer("❌ Only the team owner or an admin can remove a co-owner.")
                return
        else:
            team = await get_team_by_owner(session, tournament.id, message.from_user.id)
            if not team:
                await message.answer("❌ You are not a team owner. Use /delete_coowner TTT with a team code.")
                return

        if not team.co_owner_telegram_id:
            await message.answer(f"❌ {team.name} ({team.short_code}) has no co-owner.")
            return

        coowner_name = f"@{team.co_owner_username}" if team.co_owner_username else "the co-owner"
        removed_coowner_id = team.co_owner_telegram_id
        removed_code = team.short_code
        team_db = await session.get(Team, team.id)
        team_db.co_owner_telegram_id = None
        team_db.co_owner_username = None
        await session.commit()

    # Clear the co-owner group tag (best-effort)
    from app.services.group_tags import clear_group_tag, co_owner_title
    await clear_group_tag(message.bot, message.chat.id, removed_coowner_id, co_owner_title(removed_code))

    await message.answer(f"✅ Removed co-owner ({coowner_name}) from {team.name} ({team.short_code}).")



async def _get_team_spent(session, tournament_id: int, team_id: int) -> Decimal:
    """Get total amount spent by a team (incl. trade purse adjustments)."""
    from sqlalchemy import func
    result = await session.execute(
        select(func.coalesce(func.sum(AuctionResult.final_bid_cr), 0))
        .where(
            AuctionResult.tournament_id == tournament_id,
            AuctionResult.winning_team_id == team_id,
            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
        )
    )
    team = await session.get(Team, team_id)
    adj = Decimal(str(team.purse_adjustment_cr or 0)) if team else Decimal("0")
    return Decimal(str(result.scalar() or 0)) + adj



async def _validate_trade(session, tournament, from_team, to_team, from_player, to_player):
    """Validate a trade won\'t exceed overseas or player caps.
    Returns None if valid, or an error message string."""
    from app.utils.enums import AuctionPlayerStatus
    
    # Count current players for each team
    from_count_result = await session.execute(
        select(func.count(AuctionResult.id))
        .where(
            AuctionResult.tournament_id == tournament.id,
            AuctionResult.winning_team_id == from_team.id,
            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
        )
    )
    from_count = int(from_count_result.scalar() or 0)
    
    to_count_result = await session.execute(
        select(func.count(AuctionResult.id))
        .where(
            AuctionResult.tournament_id == tournament.id,
            AuctionResult.winning_team_id == to_team.id,
            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
        )
    )
    to_count = int(to_count_result.scalar() or 0)
    
    # Count overseas for each team
    from_ovr_result = await session.execute(
        select(func.count(AuctionResult.id))
        .join(Player, Player.id == AuctionResult.player_id)
        .where(
            AuctionResult.tournament_id == tournament.id,
            AuctionResult.winning_team_id == from_team.id,
            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            Player.is_overseas == True,
        )
    )
    from_overseas = int(from_ovr_result.scalar() or 0)
    
    to_ovr_result = await session.execute(
        select(func.count(AuctionResult.id))
        .join(Player, Player.id == AuctionResult.player_id)
        .where(
            AuctionResult.tournament_id == tournament.id,
            AuctionResult.winning_team_id == to_team.id,
            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            Player.is_overseas == True,
        )
    )
    to_overseas = int(to_ovr_result.scalar() or 0)
    
    # Check: from_team loses from_player, gains to_player
    from_new_count = from_count - 1 + 1  # same count (swap)
    to_new_count = to_count - 1 + 1
    
    from_new_overseas = from_overseas
    if from_player.is_overseas:
        from_new_overseas -= 1
    if to_player.is_overseas:
        from_new_overseas += 1
    
    to_new_overseas = to_overseas
    if to_player.is_overseas:
        to_new_overseas -= 1
    if from_player.is_overseas:
        to_new_overseas += 1
    
    # Validate counts
    if from_new_count > tournament.max_players_per_team:
        return f"Trade rejected: {from_team.name} would have {from_new_count} players (max {tournament.max_players_per_team})."
    if to_new_count > tournament.max_players_per_team:
        return f"Trade rejected: {to_team.name} would have {to_new_count} players (max {tournament.max_players_per_team})."
    if from_new_overseas > tournament.max_overseas_players:
        return f"Trade rejected: {from_team.name} would have {from_new_overseas} overseas players (max {tournament.max_overseas_players})."
    if to_new_overseas > tournament.max_overseas_players:
        return f"Trade rejected: {to_team.name} would have {to_new_overseas} overseas players (max {tournament.max_overseas_players})."
    
    return None  # Valid


@router.message(Command("reject_trade"))
async def reject_trade(message: Message, state: FSMContext) -> None:
    """Reject a pending trade."""
    if message.from_user is None:
        return
    data = _get_pending_trade(message.from_user.id)
    if not data:
        await message.answer("No active trade to reject.")
        return
    await message.answer("❌ Trade rejected.")
    # Notify the sender
    from_owner_id = data.get("from_owner_id")
    if from_owner_id:
        try:
            await message.bot.send_message(from_owner_id, "❌ Your trade proposal was rejected.")
        except Exception:
            pass


# =====================================================
# Admin: Upload GIF files and save Telegram file_id/unique_id
# =====================================================

GIF_FILE_KEYS = {
    "bid1": "bid1.gif",
    "bid2": "bid2.gif",
    "bid3": "bid3.gif",
    "bid4": "bid4.gif",
    "once": "once.jpg",
    "twice": "twice.jpg",
    "sold": "sold.gif",
    "unsold": "unsold.gif",
}


@router.message(Command("image_change_generator"), AdminFilter())
async def image_change_generator(message: Message) -> None:
    """Upload GIF/image files to Telegram and save file_ids.
    
    Send: /image_change_generator
    Then send GIFs/images as replies with captions:
      bid1, bid2, bid3, once, twice, sold, unsold
    
    Or send them in order (bid1, bid2, bid3, once, twice, sold, unsold)
    and the bot will auto-detect.
    """
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    
    await message.answer(
        "Media File ID Generator\n\n"
        "Send your GIF/image files as replies to this message.\n\n"
        "Format: Reply with a file and caption = the key name\n"
        "Example: Send a GIF with caption \"bid1\", then \"bid2\", etc.\n\n"
        "Supported keys: bid1, bid2, bid3, once, twice, sold, unsold\n\n"
        "Or use /upload_gif <key> to upload a file by replying to it."
    )


@router.message(Command("save_all_media"), AdminFilter())
async def save_all_media(message: Message) -> None:
    """Scan data/ folder, upload all GIFs/images to Telegram, save file_ids.
    
    Run this once to cache all media file_ids.
    The bot will send each file to Telegram and save the returned file_id.
    """
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    
    from app.bot.handlers.auction import _media_file_ids
    
    sent_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Load existing cache from DB
    from app.bot.handlers.auction import _load_media_from_db, _media_file_ids
    await _load_media_from_db()
    
    print(f"Loaded {len(_media_file_ids)} cached file IDs from DB")
    
    for key, filename in GIF_FILE_KEYS.items():
        # Skip if already cached in DB
        if key in _media_file_ids and _media_file_ids[key]:
            await message.answer(f"Skipping {key}: already cached (file_id exists)")
            skipped_count += 1
            continue
        filepath = os.path.join("data", filename)
        if not os.path.exists(filepath):
            await message.answer(f"Skipping {key}: {filepath} not found")
            skipped_count += 1
            continue

        try:
            import asyncio
            ext = os.path.splitext(filename)[1].lower()
            # Detect real file format from header bytes
            with open(filepath, 'rb') as fh:
                header = fh.read(10)
            is_gif = header[:6] in (b'GIF89a', b'GIF87a')
            is_jpeg = header[:2] == b'\xff\xd8'
            is_mp4 = b'ftyp' in header

            if is_jpeg or ext in ('.jpg', '.jpeg', '.png'):
                sent = await message.answer_photo(
                    FSInputFile(filepath),
                    caption=f"MEDIA:{key}"
                )
                if sent.photo:
                    file_id = sent.photo[-1].file_id
                    unique_id = sent.photo[-1].file_unique_id
                else:
                    failed_count += 1
                    continue
            elif is_gif:
                sent = await message.bot.send_animation(
                    message.chat.id,
                    FSInputFile(filepath),
                    caption=f"MEDIA:{key}"
                )
                if sent.animation:
                    file_id = sent.animation.file_id
                    unique_id = sent.animation.file_unique_id
                else:
                    failed_count += 1
                    continue
            elif is_mp4:
                # MP4 files (renamed from .mp4) - send as video
                sent = await message.bot.send_video(
                    message.chat.id,
                    FSInputFile(filepath),
                    caption=f"MEDIA:{key}"
                )
                if sent.video:
                    file_id = sent.video.file_id
                    unique_id = sent.video.file_unique_id
                else:
                    failed_count += 1
                    continue
            else:
                await message.answer(f"Unknown format for {key}")
                failed_count += 1
                continue

            # Save to database
            from app.bot.handlers.auction import _save_media_to_db
            media_type = "photo" if key in ("once", "twice") else "animation"
            local_path = GIF_FILE_KEYS.get(key)
            await _save_media_to_db(key, file_id, unique_id, local_path, media_type)
            sent_count += 1
            await message.answer(
                f"Saved {key}\n"
                f"File ID: {file_id}\n"
                f"Unique ID: {unique_id}"
            )
            # Wait 3 seconds between uploads to avoid rate limits
            await asyncio.sleep(3)
        except Exception as e:
            failed_count += 1
            await message.answer(f"Failed {key}: {e}")
    
    await message.answer(
        f"Done!\n\n"
        f"Saved: {sent_count}\n"
        f"Skipped (already cached): {skipped_count}\n"
        f"Failed: {failed_count}"
    )

