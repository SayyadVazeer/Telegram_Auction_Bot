import asyncio
import logging
import os
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.bot.filters.admin import AdminFilter
from app.bot.keyboards.auction import (
    auction_keyboard,
    category_keyboard,
    set_selection_keyboard,
    timer_keyboard,
)
from app.bot.states.auction_states import AuctionStates
from app.database.session import AsyncSessionLocal
from app.database.models.auction import AuctionPlayer, AuctionResult, AuctionRun
from app.database.models.player import Player
from app.database.models.team import Team
from app.database.models.tournament import Tournament
from app.services.auction_runtime import AuctionRuntime
from app.services.auction_service import AuctionService, BidValidationError
from app.services.tournament_service import TournamentService
from app.services.sold_card import render_sold_card, render_unsold_card
from app.utils.enums import AuctionResultStatus, AuctionPlayerStatus

router = Router()

# ── Media file IDs (loaded from DB on first use) ──
_media_file_ids: dict[str, str] = {}  # in-memory cache, loaded from DB
_media_loaded = False  # whether we've loaded from DB yet


async def _load_media_from_db():
    """Load all media file_ids from database into memory cache."""
    global _media_loaded
    if _media_loaded:
        return
    try:
        from app.database.models.media import MediaFile
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MediaFile.key, MediaFile.telegram_file_id))
            for key, file_id in result.all():
                _media_file_ids[key] = file_id
        _media_loaded = True
    except Exception:
        pass  # Table may not exist yet


async def _save_media_to_db(key: str, file_id: str, unique_id: str | None, local_path: str | None, media_type: str):
    """Save a media file_id to database and in-memory cache."""
    from datetime import datetime
    from app.database.models.media import MediaFile
    _media_file_ids[key] = file_id
    try:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(MediaFile).where(MediaFile.key == key))
            obj = existing.scalar_one_or_none()
            if obj:
                obj.telegram_file_id = file_id
                obj.telegram_unique_id = unique_id
                obj.updated_at = datetime.utcnow()
            else:
                obj = MediaFile(
                    key=key,
                    telegram_file_id=file_id,
                    telegram_unique_id=unique_id,
                    local_path=local_path,
                    media_type=media_type,
                )
                session.add(obj)
            await session.commit()
        logging.info("Saved media %s: file_id=%s", key, file_id[:30] if file_id else "None")
    except Exception as e:
        logging.error("Failed to save media %s to DB: %s", key, e)
        # Still cache in memory even if DB fails
        _media_file_ids[key] = file_id

# Inter-player delay
INTER_PLAYER_DELAY = 15  # seconds between players

# ── helpers ────────────────────────────────────────────────────────

async def _tournament_for_chat(chat_id: int):
    async with AsyncSessionLocal() as session:
        return await TournamentService(session).get_by_telegram_chat_id(chat_id)


async def _get_set_status(session, tournament_id: int, set_number: int):
    """Return (pending, unsold, sold, total) counts for a specific set.
    Pending = players with NO auction results at all (fresh).
    Unsold = players that were UNSOLD in previous runs, not currently SOLD."""
    set_player_result = await session.execute(
        select(Player.id).where(Player.set_number == set_number)
    )
    set_player_ids = set(set_player_result.scalars().all())
    total = len(set_player_ids)
    if total == 0:
        return 0, 0, 0, 0
    from sqlalchemy import func as sa_func, desc
    # Get the latest result for each player
    latest_result = await session.execute(
        select(AuctionResult.player_id, AuctionResult.result_status)
        .where(
            AuctionResult.tournament_id == tournament_id,
            AuctionResult.player_id.in_(set_player_ids),
        )
        .order_by(desc(AuctionResult.id))
    )
    seen = set()
    sold_count = 0
    unsold_count = 0
    for player_id, status in latest_result.all():
        if player_id not in seen:
            seen.add(player_id)
            if status == AuctionResultStatus.SOLD.value:
                sold_count += 1
            elif status == AuctionResultStatus.UNSOLD.value:
                unsold_count += 1
    # Pending = players with NO auction results at all
    pending_count = total - len(seen)
    return pending_count, unsold_count, sold_count, total


def _live_text(player, team, bid_cr, bid_timer, bidder_username=None):
    """Build the live auction message text."""
    overseas = ' ✈️' if player.is_overseas else ''
    lines = [
        f"🔴 LIVE AUCTION",
        "",
        f"{player.name}{overseas}",
        f"Role: {player.role}",
        f"Base price: Rs.{Decimal(str(player.base_price_cr)):.2f} Cr",
        "",
    ]
    if bid_cr and team:
        lines.extend([
            f"Highest bid: Rs.{bid_cr:.2f} Cr",
            f"By: {team.name} ({team.short_code})",
        ])
        if bidder_username:
            lines.append(f"Bid by: @{bidder_username}")
    else:
        lines.append("No bids received")
    lines.extend(["", f"Place your bid with /b <amount> in {bid_timer} seconds."])
    return "\n".join(lines)


async def _send_media(bot, chat_id: int, media_key: str, fallback_path: str, caption: str = "", parse_mode: str = None):
    """Send media using file_id first, falling back to local file.
    
    media_key: 'bid1', 'bid2', 'bid3', 'once', 'twice', 'sold', 'unsold'
    fallback_path: local file path if file_id not available
    
    Detects real format from file header:
    - JPEG → send_photo
    - GIF → send_animation  
    - MP4 → send_video
    """
    # Ensure DB cache is loaded
    await _load_media_from_db()
    
    # Try file_id first
    file_id = _media_file_ids.get(media_key)
    if file_id:
        try:
            if media_key in ('once', 'twice'):
                # These are JPEG - send as photo
                await bot.send_photo(chat_id, file_id, caption=caption, parse_mode=parse_mode)
            else:
                # Try animation first (GIF), fall back to video (MP4)
                try:
                    await bot.send_animation(chat_id, file_id, caption=caption, parse_mode=parse_mode)
                except Exception:
                    await bot.send_video(chat_id, file_id, caption=caption, parse_mode=parse_mode)
            return
        except Exception:
            pass  # File ID may have expired, fall through to local file

    # Fallback to local file
    if os.path.exists(fallback_path):
        try:
            # Detect real format from file header
            with open(fallback_path, 'rb') as fh:
                header = fh.read(10)
            is_gif = header[:6] in (b'GIF89a', b'GIF87a')
            is_jpeg = header[:2] == b'\xff\xd8'
            is_mp4 = b'ftyp' in header

            if is_jpeg:
                await bot.send_photo(chat_id, FSInputFile(fallback_path), caption=caption, parse_mode=parse_mode)
            elif is_gif:
                await bot.send_animation(chat_id, FSInputFile(fallback_path), caption=caption, parse_mode=parse_mode)
            elif is_mp4:
                await bot.send_video(chat_id, FSInputFile(fallback_path), caption=caption, parse_mode=parse_mode)
            else:
                # Unknown format - try animation
                await bot.send_animation(chat_id, FSInputFile(fallback_path), caption=caption, parse_mode=parse_mode)
            return
        except Exception:
            pass

    # Last resort - just send caption as text
    if caption:
        await bot.send_message(chat_id, caption, parse_mode=parse_mode)


async def _send_active_player(bot, chat_id: int, auction_run_id: int) -> None:
    """Select the next player and send the live auction announcement."""
    async with AsyncSessionLocal() as session:
        service = AuctionService(session)
        run = await session.get(AuctionRun, auction_run_id)
        if run is None:
            return

        state = AuctionRuntime.get(auction_run_id)
        if state is None or state.paused or state.stopped:
            return

        # Get category from runtime
        rt_state = AuctionRuntime.get(run.id)
        cat = rt_state.category if rt_state else "pending"
        player_row = await service.prepare_next_player(run, category=cat)
        if player_row is None:
            await service.complete_auction_run(run)
            await session.commit()
            AuctionRuntime.remove(auction_run_id)
            await bot.send_message(
                chat_id,
                f"Set {run.set_number} is complete. No eligible players remain.",
            )
            return
        await service.activate_player(player_row)
        player = await session.get(Player, player_row.player_id)
        tournament = await TournamentService(session).get_by_telegram_chat_id(chat_id)
        await session.commit()

    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.paused or state.stopped:
        return

    state.current_auction_player_id = player_row.id
    text = _live_text(player, None, None, state.bid_timer_seconds)
    min_inc = Decimal(str(run.minimum_bid_increment_cr))
    markup = auction_keyboard(
        min_inc,
        is_admin=True,
    )

    # Send with player photo using file_id first
    if player.telegram_file_id:
        try:
            sent = await bot.send_photo(chat_id, player.telegram_file_id, caption=text, reply_markup=markup)
        except Exception:
            sent = await bot.send_message(chat_id, text, reply_markup=markup)
    elif player.telegram_photo_path and os.path.exists(player.telegram_photo_path):
        try:
            sent = await bot.send_photo(chat_id, FSInputFile(player.telegram_photo_path), caption=text, reply_markup=markup)
        except Exception:
            sent = await bot.send_message(chat_id, text, reply_markup=markup)
    else:
        sent = await bot.send_message(chat_id, text, reply_markup=markup)

    state.live_message_id = sent.message_id
    state.on_timer_expired = lambda: _on_timer_expired(bot, chat_id, auction_run_id)
    await AuctionRuntime.start_timer(state, state.on_timer_expired)


async def _finalize_player(bot, chat_id: int, auction_run_id: int) -> None:
    """Finalize current player as SOLD or UNSOLD and move to next."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.current_auction_player_id is None:
        return

    try:
        async with AsyncSessionLocal() as session:
            service = AuctionService(session)
            row = (
                await session.execute(
                    select(AuctionPlayer)
                    .options(selectinload(AuctionPlayer.auction_run))
                    .where(AuctionPlayer.id == state.current_auction_player_id)
                )
            ).scalar_one_or_none()

            if row is None or row.status != AuctionPlayerStatus.ACTIVE.value:
                return

            player = await session.get(Player, row.player_id)
            if row.current_team_id is None:
                await service.complete_player_unsold(row)
                result_text = f"❌ UNSOLD -- {player.name}"
                team = None
            else:
                team = await session.get(Team, row.current_team_id)
                await service.complete_player_sold(
                    row, team, Decimal(str(row.current_bid_cr))
                )
                auction_run_obj = row.auction_run
                tournament = await session.get(Tournament, auction_run_obj.tournament_id) if auction_run_obj else None
                remaining_purse = "?"
                remaining_players = "?"
                remaining_overseas = "?"
                if tournament:
                    from sqlalchemy import func as sa_func
                    tsr = await session.execute(
                        select(sa_func.coalesce(sa_func.sum(AuctionResult.final_bid_cr), 0))
                        .where(
                            AuctionResult.tournament_id == tournament.id,
                            AuctionResult.winning_team_id == team.id,
                            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                        )
                    )
                    total_spent = Decimal(str(tsr.scalar() or 0))
                    total_spent += Decimal(str(row.current_bid_cr))
                    remaining_purse = f"Rs.{tournament.purse_cr - total_spent:.2f} Cr"
                    pr = await session.execute(
                        select(sa_func.count(AuctionResult.id))
                        .where(
                            AuctionResult.tournament_id == tournament.id,
                            AuctionResult.winning_team_id == team.id,
                            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                        )
                    )
                    team_count = int(pr.scalar() or 0)
                    remaining_players = f"{tournament.max_players_per_team - team_count}/{tournament.max_players_per_team}"
                    ovr = await session.execute(
                        select(sa_func.count(AuctionResult.id))
                        .join(Player, Player.id == AuctionResult.player_id)
                        .where(
                            AuctionResult.tournament_id == tournament.id,
                            AuctionResult.winning_team_id == team.id,
                            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                            Player.is_overseas == True,
                        )
                    )
                    overseas_count = int(ovr.scalar() or 0)
                    remaining_overseas = f"{tournament.max_overseas_players - overseas_count}/{tournament.max_overseas_players}"
                owner_display = f"@{team.owner_username}" if team.owner_username else "Owner"
                result_text = f"✅ SOLD -- {player.name} to {team.name} ({team.short_code})\n👤 Owner: {owner_display}\n💰 Amount: Rs.{row.current_bid_cr:.2f} Cr\n💵 Remaining purse: {remaining_purse}\n👥 Squad: {remaining_players} | ✈️ Overseas: {remaining_overseas}"
            await session.commit()

        # Send sold/unsold card
        if row.current_team_id is not None:
            card = await render_sold_card(
                bot, player, team, Decimal(str(row.current_bid_cr)),
                owner_username=team.owner_username,
            )
            await bot.send_photo(
                chat_id,
                BufferedInputFile(card, filename="sold.png"),
                caption=result_text,
            )
        else:
            card = await render_unsold_card(bot, player)
            await bot.send_photo(
                chat_id,
                BufferedInputFile(card, filename="unsold.png"),
                caption=result_text,
            )

        state.current_auction_player_id = None
        state.last_call_task = None
        
        # Wait 15 seconds between players (with /next_player skip support)
        state.waiting_for_next = True
        await asyncio.sleep(INTER_PLAYER_DELAY)
        state.waiting_for_next = False

        # Check state again before sending next player
        if AuctionRuntime.get(auction_run_id) is state and not state.paused and not state.stopped:
            await _send_active_player(bot, chat_id, auction_run_id)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Finalize player failed for auction_run_id=%s", auction_run_id)
        return


async def _on_sold_warning(bot, chat_id: int, auction_run_id: int) -> None:
    """15-second warning for player WITH bids: GOING ONCE at 10s, GOING TWICE at 5s, SOLD at 0s."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.current_auction_player_id is None:
        return

    try:
        state.last_call_task = asyncio.current_task()

        # 10 seconds left - GOING ONCE
        if AuctionRuntime.get(auction_run_id) is not state or state.stopped:
            return
        bid_text = ""
        async with AsyncSessionLocal() as sess:
            ap = await sess.get(AuctionPlayer, state.current_auction_player_id)
            if ap and ap.current_team_id and ap.current_bid_cr:
                tm = await sess.get(Team, ap.current_team_id)
                if tm:
                    owner = f"@{tm.owner_username}" if tm.owner_username else "Owner"
                    bid_text = f"\n\nCurrent highest bid: Rs.{ap.current_bid_cr:.2f} Cr\nTeam: {tm.name} ({tm.short_code})\nOwner: {owner}"
        
        await _send_media(
            bot, chat_id, "once", os.path.join("data", "once.jpg"),
            caption=f"🔴 GOING ONCE -- Place your bid now!{bid_text}"
        )
        await asyncio.sleep(5)

        # 5 seconds left - GOING TWICE
        if AuctionRuntime.get(auction_run_id) is not state or state.stopped:
            return
        bid_text2 = ""
        async with AsyncSessionLocal() as sess2:
            ap2 = await sess2.get(AuctionPlayer, state.current_auction_player_id)
            if ap2 and ap2.current_team_id and ap2.current_bid_cr:
                tm2 = await sess2.get(Team, ap2.current_team_id)
                if tm2:
                    owner2 = f"@{tm2.owner_username}" if tm2.owner_username else "Owner"
                    bid_text2 = f"\n\nCurrent highest bid: Rs.{ap2.current_bid_cr:.2f} Cr\nTeam: {tm2.name} ({tm2.short_code})\nOwner: {owner2}"
        
        await _send_media(
            bot, chat_id, "twice", os.path.join("data", "twice.jpg"),
            caption=f"🟡 GOING TWICE -- Last chance!{bid_text2}"
        )
        await asyncio.sleep(5)

        # 0 seconds - SOLD gif + finalize together
        if AuctionRuntime.get(auction_run_id) is not state or state.stopped:
            return
        await _send_media(
            bot, chat_id, "sold", os.path.join("data", "sold.gif"),
            caption="✅ SOLD!"
        )

        await _finalize_player(bot, chat_id, auction_run_id)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Sold warning failed for auction_run_id=%s", auction_run_id)
        return


async def _on_unsold_warning(bot, chat_id: int, auction_run_id: int) -> None:
    """Timer expired with NO bids - show unsold warning for 15s, then finalize."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.current_auction_player_id is None:
        return

    try:
        state.last_call_task = asyncio.current_task()

        # Get player info for the message
        async with AsyncSessionLocal() as sess:
            ap = await sess.get(AuctionPlayer, state.current_auction_player_id)
            if not ap:
                return
            player = await sess.get(Player, ap.player_id)
            if not player:
                return

        # Send unsold warning GIF
        unsold_text = (
            f"⚠️ {player.name} is going to be UNSOLD\n"
            f"Base price: Rs.{Decimal(str(player.base_price_cr)):.2f} Cr\n"
            f"Role: {player.role}\n\n"
            "Did I hear any final bids?"
        )
        await _send_media(
            bot, chat_id, "unsold", os.path.join("data", "unsold.gif"),
            caption=unsold_text
        )

        # Wait 15 seconds for any final bids
        await asyncio.sleep(15)

        # Check if someone bid during the 15s unsold timer
        if AuctionRuntime.get(auction_run_id) is not state or state.stopped:
            return

        # Check if any bids came in during the 15s
        async with AsyncSessionLocal() as sess2:
            ap2 = await sess2.get(AuctionPlayer, state.current_auction_player_id)
            if ap2 and ap2.current_team_id is not None:
                # Someone bid during unsold timer - run sold warning instead
                await _on_sold_warning(bot, chat_id, auction_run_id)
                return

        # Still no bids - finalize as unsold
        await _finalize_player(bot, chat_id, auction_run_id)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Unsold warning failed for auction_run_id=%s", auction_run_id)
        return


async def _on_timer_expired(bot, chat_id: int, auction_run_id: int) -> None:
    """Normal timer expired -- check if bids exist, then warn or unsold."""
    state = AuctionRuntime.get(auction_run_id)
    if state is None or state.paused or state.stopped:
        return

    # Check if anyone has bid
    has_bids = False
    if state.current_auction_player_id:
        async with AsyncSessionLocal() as session:
            row = await session.get(AuctionPlayer, state.current_auction_player_id)
            if row and row.current_team_id is not None:
                has_bids = True

    if has_bids:
        # Player has bids -- run GOING ONCE / GOING TWICE warning
        await _on_sold_warning(bot, chat_id, auction_run_id)
    else:
        # No bids -- run unsold warning (15s timer)
        await _on_unsold_warning(bot, chat_id, auction_run_id)


@router.message(Command("start_auction"), AdminFilter())
async def start_auction_command(message: Message, state: FSMContext) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return

    await state.clear()

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured for this group.")
            return

        if await AuctionService(session).get_running_auction(tournament.id):
            await message.answer("Auction already running. Stop it first.")
            return

        result = await session.execute(
            select(Player.set_number).distinct().order_by(Player.set_number)
        )
        set_numbers = [row[0] for row in result.all()]

    if not set_numbers:
        await message.answer("No players loaded. Import players first.")
        return

    await state.set_state(AuctionStates.choosing_set_number)
    await message.answer(
        "Select the set to auction:",
        reply_markup=set_selection_keyboard(set_numbers),
    )


@router.callback_query(F.data == "auction:cancel_start")
async def auction_cancel_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Auction cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("auction:set:"), AuctionStates.choosing_set_number)
async def auction_set_selected(callback: CallbackQuery, state: FSMContext) -> None:
    set_number = int(callback.data.split(":")[-1])

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        if not tournament:
            await callback.answer("No tournament found.", show_alert=True)
            return
        pending, unsold, sold, total = await _get_set_status(session, tournament.id, set_number)

    await state.update_data(set_number=set_number)
    await state.set_state(AuctionStates.choosing_category)

    status_text = (
        f"Set {set_number} Status\n\n"
        f"Total: {total}\n"
        f"Pending (not yet auctioned): {pending}\n"
        f"Unsold: {unsold}\n"
        f"Sold: {sold}"
    )

    await callback.message.edit_text(
        status_text,
        reply_markup=category_keyboard(set_number, pending, unsold),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("auction:cat:"), AuctionStates.choosing_category)
async def auction_category_selected(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    category = parts[2]
    set_number = int(parts[3])

    await state.update_data(set_number=set_number, category=category)
    await state.set_state(AuctionStates.waiting_for_bid_timer)

    await callback.message.edit_text(
        f"Set {set_number} | Category: {category.title()}\n\nSelect the bid timer:",
        reply_markup=timer_keyboard(set_number, category),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("auction:timer:"), AuctionStates.waiting_for_bid_timer)
async def auction_timer_selected(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")

    if parts[2] == "custom":
        set_number = int(parts[3])
        category = parts[4]
        await state.update_data(set_number=set_number, category=category)
        await callback.message.edit_text(
            "Enter bid timer in seconds (1-600):\nUse /cancel to cancel."
        )
        await callback.answer()
        return

    set_number = int(parts[2])
    category = parts[3]
    bid_timer = int(parts[4])

    await state.update_data(bid_timer=bid_timer)
    await state.set_state(AuctionStates.waiting_for_min_increment)
    await callback.message.edit_text(
        f"Set {set_number} | {category.title()} | Timer: {bid_timer}s\n\n"
        "Select the minimum bid increment:",
    )
    await callback.answer()


@router.message(AuctionStates.waiting_for_bid_timer)
async def auction_custom_timer(message: Message, state: FSMContext) -> None:
    try:
        seconds = int((message.text or "").strip())
        if seconds <= 0 or seconds > 600:
            raise ValueError
    except ValueError:
        await message.answer("Enter a timer between 1 and 600 seconds.")
        return

    data = await state.get_data()
    set_number = data["set_number"]
    category = data["category"]

    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(bid_timer=seconds)
    await state.set_state(AuctionStates.waiting_for_min_increment)
    await message.answer(
        f"Set {set_number} | {category.title()} | Timer: {seconds}s\n\n"
        "Enter the minimum bid increment in Cr (e.g. 0.25):\nUse /cancel to cancel."
    )


async def _start_auction_with_params(callback, state, set_number, category, bid_timer):
    chat_id = callback.message.chat.id
    data = await state.get_data()
    min_increment = data.get("min_increment", 0.25)
    max_increment = data.get("max_increment", 0)

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(chat_id)
        if not tournament:
            await callback.answer("No tournament found.", show_alert=True)
            return

        service = AuctionService(session)
        if await service.get_running_auction(tournament.id):
            await callback.answer("An auction is already running.", show_alert=True)
            return

        run = await service.create_auction_run(
            tournament.id, set_number, bid_timer,
            minimum_bid_increment_cr=Decimal(str(min_increment)),
            maximum_bid_increment_cr=Decimal(str(max_increment)),
        )
        await service.start_auction_run(run)
        await session.commit()

    await state.clear()
    rt = AuctionRuntime.create(run.id, chat_id, bid_timer)
    rt.category = category

    max_text = f" | Max increment: {max_increment:.2f} Cr" if max_increment > 0 else " | No max limit"
    await callback.message.edit_text(
        f"Auction started\n\n"
        f"Set {set_number} | {category.title()}\n"
        f"Timer: {bid_timer}s\n"
        f"Min increment: {min_increment:.2f} Cr\n"
        f"Max increment: {max_text}"
    )
    await callback.answer()
    await _send_active_player(callback.message.bot, chat_id, run.id)


async def _start_auction_with_params_msg(message, state, set_number, category, bid_timer):
    chat_id = message.chat.id
    data = await state.get_data()
    min_increment = data.get("min_increment", 0.25)
    max_increment = data.get("max_increment", 0)

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(chat_id)
        if not tournament:
            await message.answer("No tournament found.")
            return

        service = AuctionService(session)
        if await service.get_running_auction(tournament.id):
            await message.answer("An auction is already running.")
            return

        run = await service.create_auction_run(
            tournament.id, set_number, bid_timer,
            minimum_bid_increment_cr=Decimal(str(min_increment)),
            maximum_bid_increment_cr=Decimal(str(max_increment)),
        )
        await service.start_auction_run(run)
        await session.commit()

    await state.clear()
    rt = AuctionRuntime.create(run.id, chat_id, bid_timer)
    rt.category = category

    max_text = f"Max: {max_increment:.2f} Cr" if max_increment > 0 else "No max limit"
    await message.answer(
        f"Auction started\n\n"
        f"Set {set_number} | {category.title()}\n"
        f"Timer: {bid_timer}s | Min: {min_increment:.2f} Cr | {max_text}"
    )
    await _send_active_player(message.bot, chat_id, run.id)


# ── min bid increment selection ─────────────────────────

@router.message(AuctionStates.waiting_for_min_increment)
async def auction_custom_min_increment(message: Message, state: FSMContext) -> None:
    try:
        value = Decimal((message.text or "").strip())
        if value <= 0:
            raise ValueError
    except Exception:
        await message.answer("Enter a valid positive number (e.g. 0.25):")
        return

    data = await state.get_data()
    await state.update_data(min_increment=float(value))
    await state.set_state(AuctionStates.waiting_for_max_increment)
    set_number = data["set_number"]
    category = data["category"]
    bid_timer = data["bid_timer"]
    await message.answer(
        f"Set {set_number} | {category.title()} | Timer: {bid_timer}s | Min increment: {value:.2f} Cr\n\n"
        "Enter the maximum bid increment in Cr (0 = no limit):\nUse /cancel to cancel."
    )


# ── max bid increment selection ─────────────────────────

@router.message(AuctionStates.waiting_for_max_increment)
async def auction_custom_max_increment(message: Message, state: FSMContext) -> None:
    try:
        value = Decimal((message.text or "").strip())
        if value < 0:
            raise ValueError
    except Exception:
        await message.answer("Enter a valid number (0 for no limit):")
        return

    data = await state.get_data()
    await state.update_data(max_increment=float(value))
    set_number = data["set_number"]
    category = data["category"]
    bid_timer = data["bid_timer"]
    try:
        await message.delete()
    except Exception:
        pass
    await _start_auction_with_params_msg(message, state, set_number, category, bid_timer)

# ── admin controls ────────────────────────────────────────────────

async def _control(message: Message, action: str) -> str:
    try:
        async with AsyncSessionLocal() as session:
            tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
            if not tournament:
                return "No tournament configured for this group."
            service = AuctionService(session)
            run = await service.get_running_auction(tournament.id)
            if action == "resume" and run is None:
                run = (
                    await session.execute(
                        select(AuctionRun)
                        .where(
                            AuctionRun.tournament_id == tournament.id,
                            AuctionRun.status == "PAUSED",
                        )
                        .order_by(AuctionRun.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if not run:
                return "No matching auction run found."

            state = AuctionRuntime.get(run.id)

            if action == "pause":
                await service.pause_auction_run(run)
                if state:
                    state.paused = True
                    AuctionRuntime.cancel_timer(state)
                    AuctionRuntime.cancel_last_call(state)
                text = "Auction paused."

            elif action == "resume":
                await service.resume_auction_run(run)
                if state:
                    state.paused = False
                    state.stopped = False
                    await AuctionRuntime.restart_timer(state)
                text = "Auction resumed."

            elif action == "stop":
                # Stop even with active player - mark as not participated
                if state and state.current_auction_player_id:
                    # Cancel any running timers
                    AuctionRuntime.cancel_timer(state)
                    AuctionRuntime.cancel_last_call(state)
                    
                    # Mark the active player as unsold (not participated)
                    async with AsyncSessionLocal() as sess2:
                        ap_result = await sess2.execute(
                            select(AuctionPlayer)
                            .options(selectinload(AuctionPlayer.auction_run))
                            .where(AuctionPlayer.id == state.current_auction_player_id)
                        )
                        ap = ap_result.scalar_one_or_none()
                        if ap and ap.status == AuctionPlayerStatus.ACTIVE.value:
                            service2 = AuctionService(sess2)
                            await service2.complete_player_not_participated(ap)
                            await sess2.commit()
                    state.current_auction_player_id = None
                
                await service.stop_auction_run(run)
                if state:
                    state.stopped = True
                    state.paused = False
                    AuctionRuntime.cancel_timer(state)
                    AuctionRuntime.cancel_last_call(state)
                text = "Auction stopped."

            await session.commit()
        return text
    except ValueError as exc:
        msg = str(exc)
        if not msg.startswith("❌"):
            msg = f"❌ {msg}"
        return msg


@router.message(Command("pause_auction"), AdminFilter())
async def pause_auction(message: Message) -> None:
    await message.answer(await _control(message, "pause"))


@router.message(Command("resume_auction"), AdminFilter())
async def resume_auction(message: Message) -> None:
    await message.answer(await _control(message, "resume"))


@router.message(Command("stop_auction"), AdminFilter())
async def stop_auction(message: Message) -> None:
    await message.answer(await _control(message, "stop"))


@router.message(Command("next_player"), AdminFilter())
async def next_player_command(message: Message) -> None:
    """Skip the 15-second inter-player delay and show next player immediately."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured.")
            return
        run = await AuctionService(session).get_running_auction(tournament.id)
    
    if not run:
        await message.answer("No auction running.")
        return
    
    state = AuctionRuntime.get(run.id)
    if not state:
        await message.answer("No active auction state.")
        return
    
    if not state.waiting_for_next:
        await message.answer("No inter-player delay in progress. Wait for the current player.")
        return
    
    # Skip the delay by setting waiting_for_next = False
    state.waiting_for_next = False
    await message.answer("Skipping to next player...")


@router.message(Command("status"), AdminFilter())
async def auction_status(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("No tournament configured for this group.")
            return
        run = await AuctionService(session).get_running_auction(tournament.id)
        active = await AuctionService(session).get_active_auction_player(tournament.id) if run else None
    if not run:
        await message.answer("No auction is currently running.")
        return
    runtime = AuctionRuntime.get(run.id)
    player_text = active.player.name if active and active.player else "None"
    bid_text = f"Rs.{active.current_bid_cr:.2f} Cr" if active and active.current_bid_cr else "No bids"
    status_str = "Paused" if runtime and runtime.paused else ("Stopped" if runtime and runtime.stopped else run.status)
    await message.answer(
        f"Auction status\n\n"
        f"Set: {run.set_number}\n"
        f"Status: {status_str}\n"
        f"Active player: {player_text}\n"
        f"Current bid: {bid_text}\n"
        f"Timer: {'running' if runtime and runtime.timer_task and not runtime.paused else 'paused'}"
    )


# ── button callbacks ──────────────────────────────────────────────

def _is_admin_user(user_id: int) -> bool:
    """Check if user is an admin."""
    from app.bot.filters.admin import is_admin as _is_admin
    return _is_admin(user_id)


@router.callback_query(F.data == "auction:pause")
async def auction_pause_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    if not _is_admin_user(callback.from_user.id):
        await callback.answer("Only admins can pause the auction.", show_alert=True)
        return
    # Immediately remove keyboard to prevent double-click
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # Check if already paused
    from app.database.models.auction import AuctionRun
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        if tournament:
            run = await AuctionService(session).get_running_auction(tournament.id)
            if run:
                rt = AuctionRuntime.get(run.id)
                if rt and rt.paused:
                    await callback.answer("Already paused.", show_alert=True)
                    return
    result = await _control(callback.message, "pause")
    if result.startswith("❌"):
        await callback.answer(result, show_alert=True)
    else:
        await callback.answer()
        await callback.message.answer("⏸️ Auction PAUSED.")


@router.callback_query(F.data == "auction:resume")
async def auction_resume_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    if not _is_admin_user(callback.from_user.id):
        await callback.answer("Only admins can resume the auction.", show_alert=True)
        return
    # Immediately remove keyboard to prevent double-click
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    result = await _control(callback.message, "resume")
    if result.startswith("❌"):
        await callback.answer(result, show_alert=True)
    else:
        await callback.answer()
        await callback.message.answer("▶️ Auction RESUMED!")


@router.callback_query(F.data == "auction:stop")
async def auction_stop_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    if not _is_admin_user(callback.from_user.id):
        await callback.answer("Only admins can stop the auction.", show_alert=True)
        return
    # Immediately remove keyboard to prevent double-click
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # Check if already stopped
    from app.database.models.auction import AuctionRun
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        if tournament:
            run = await AuctionService(session).get_running_auction(tournament.id)
            if run:
                rt = AuctionRuntime.get(run.id)
                if rt and rt.stopped:
                    await callback.answer("Already stopped.", show_alert=True)
                    return
    result = await _control(callback.message, "stop")
    if result.startswith("❌"):
        await callback.answer(result, show_alert=True)
    else:
        await callback.answer()
        await callback.message.answer("⏹️ Auction STOPPED.")


@router.callback_query(F.data == "auction:refresh")
async def auction_refresh(callback: CallbackQuery) -> None:
    await callback.answer("Info refreshes when a bid is placed.")


# ── bidding ───────────────────────────────────────────────────────

async def _button_bid(message: Message, user_id: int, amount: Decimal | None, increment: Decimal | None = None) -> str:
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            return "No tournament configured."
        service = AuctionService(session)
        run = await service.get_running_auction(tournament.id)
        if not run:
            return "Auction is not running."
        rt = AuctionRuntime.get(run.id)
        if rt and rt.paused:
            return "Auction is paused."
        if rt and rt.stopped:
            return "Auction is stopped."
        team = await service.get_team_by_owner(user_id, tournament.id)
        active = await service.get_active_auction_player(tournament.id)
        if not team:
            return "You are not registered as a team owner."
        if not active:
            return "No active player being auctioned."
        player = active.player

        if active.current_team_id and active.current_team_id == team.id:
            return "You already have the highest bid!"

        bid = amount
        if bid is None:
            current = Decimal(str(active.current_bid_cr)) if active.current_bid_cr is not None else Decimal(str(player.base_price_cr))
            bid = current + increment
            if active.current_bid_cr is None:
                bid = max(Decimal(str(player.base_price_cr)), bid)
        from app.database.models.auction import AuctionRun
        auction_run = await session.get(AuctionRun, active.auction_run_id)
        run_min_inc = Decimal(str(auction_run.minimum_bid_increment_cr)) if auction_run else Decimal("0.25")
        try:
            await service.place_bid(active, team, tournament, bid, run_min_inc, user_id)
        except BidValidationError as exc:
            await session.rollback()
            return str(exc)
        await session.commit()

        runtime = AuctionRuntime.get(active.auction_run_id)
        if runtime and runtime.live_message_id:
            try:
                text = _live_text(
                    player, team, bid, runtime.bid_timer_seconds,
                    bidder_username=team.owner_username,
                )
                run_min = Decimal(str(auction_run.minimum_bid_increment_cr)) if auction_run else Decimal("0.25")
                markup = auction_keyboard(
                    run_min,
                    is_admin=True,
                )
                try:
                    await message.bot.edit_message_caption(
                        chat_id=message.chat.id,
                        message_id=runtime.live_message_id,
                        caption=text,
                        reply_markup=markup,
                    )
                except Exception:
                    try:
                        await message.bot.edit_message_text(
                            text=text,
                            chat_id=message.chat.id,
                            message_id=runtime.live_message_id,
                            reply_markup=markup,
                        )
                    except Exception:
                        pass
            except Exception:
                pass

    runtime = AuctionRuntime.get(active.auction_run_id)
    if runtime:
        await AuctionRuntime.restart_timer(runtime)

    owner_display = f"@{team.owner_username}" if team.owner_username else "Owner"
    return f"🔨 {team.name} ({team.short_code}) \u2192 Rs.{bid:.2f} Cr\nOwner: {owner_display}\nPlayer: {player.name}"


@router.callback_query(F.data.startswith("auction:bid_increment:"))
async def auction_increment_bid(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    increment = Decimal(callback.data.rsplit(":", 1)[-1])
    result = await _button_bid(callback.message, callback.from_user.id, None, increment)
    error_keywords = ["❌", "⚠", "not running", "paused", "stopped", "no active", "not registered", "already", "insufficient"]
    is_error = any(kw in result.lower() for kw in error_keywords)
    if is_error:
        await callback.answer(result, show_alert=True)
    else:
        await callback.answer()
        owner_display = f"@{callback.from_user.username}" if callback.from_user.username else "Owner"
        lines = result.split("\n")
        team_line = lines[0] if lines else result
        bid_msg = (
            f"🔨 BID\n\n"
            f"{team_line}\n"
            f"🧑 Owner: {owner_display}\n\n"
            f"Do I hear anyone else?"
        )
        # Rotate through bid1, bid2, bid3, bid4
        bid_counter = getattr(auction_increment_bid, '_counter', 0) + 1
        auction_increment_bid._counter = bid_counter
        bid_num = (bid_counter % 4) + 1
        await _send_media(
            callback.message.bot, callback.message.chat.id,
            f"bid{bid_num}", os.path.join("data", f"bid{bid_num}.gif"),
            caption=bid_msg
        )


@router.callback_query(F.data == "auction:custom_bid")
async def auction_custom_bid(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AuctionStates.waiting_for_custom_bid)
    await callback.message.answer("Enter your bid amount in Cr, for example: 4.70\nUse /cancel to cancel.")
    await callback.answer()


@router.message(AuctionStates.waiting_for_custom_bid)
async def auction_custom_bid_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal((message.text or "").strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer("Enter a positive amount (e.g. 4.70).")
        return
    result = await _button_bid(message, message.from_user.id, amount)
    await state.clear()
    await message.answer(result)
