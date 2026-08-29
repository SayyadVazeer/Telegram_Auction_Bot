import asyncio
import logging
import os
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import FSInputFile
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
from app.services.auction_runtime import AuctionRuntime
from app.services.auction_service import AuctionService, BidValidationError
from app.services.tournament_service import TournamentService
from app.services.sold_card import render_sold_card, render_unsold_card
from app.utils.enums import AuctionResultStatus, AuctionPlayerStatus

router = Router()


# ── helpers ────────────────────────────────────────────────────────

async def _tournament_for_chat(chat_id: int):
    async with AsyncSessionLocal() as session:
        return await TournamentService(session).get_by_telegram_chat_id(chat_id)


async def _get_set_status(session, tournament_id: int, set_number: int):
    """Return (pending, unsold, sold, total) counts for a specific set."""
    # Get all player IDs in this set
    set_player_result = await session.execute(
        select(Player.id).where(Player.set_number == set_number)
    )
    set_player_ids = set(set_player_result.scalars().all())
    total = len(set_player_ids)

    if total == 0:
        return 0, 0, 0, 0

    # Count sold players in THIS set only
    sold_result = await session.execute(
        select(AuctionResult.player_id)
        .where(
            AuctionResult.tournament_id == tournament_id,
            AuctionResult.player_id.in_(set_player_ids),
            AuctionResult.result_status == AuctionResultStatus.SOLD.value,
        )
    )
    sold_count = len(set(sold_result.scalars().all()))

    # Count unsold players in THIS set only
    unsold_result = await session.execute(
        select(AuctionResult.player_id)
        .where(
            AuctionResult.tournament_id == tournament_id,
            AuctionResult.player_id.in_(set_player_ids),
            AuctionResult.result_status == AuctionResultStatus.UNSOLD.value,
        )
    )
    unsold_count = len(set(unsold_result.scalars().all()))

    pending_count = total - sold_count - unsold_count

    return pending_count, unsold_count, sold_count, total


def _live_text(player, team, bid_cr, bid_timer, bidder_username=None):
    """Build the live auction message text."""
    lines = [
        "🔴 LIVE AUCTION",
        "",
        f"{player.name} {'(Overseas)' if player.is_overseas else ''}",
        f"Role: {player.role}",
        f"Base price: Rs.{Decimal(str(player.base_price_cr)):.2f} Cr",
    ]
    if bid_cr and team:
        lines.extend([
            "",
            f"Highest bid: Rs.{bid_cr:.2f} Cr",
            f"By: {team.name} ({team.short_code})",
        ])
        if bidder_username:
            lines.append(f"Owner: @{bidder_username}")
    else:
        lines.extend(["", "No bids yet."])
    lines.extend(["", f"Place your bid in {bid_timer} seconds."])
    return "\n".join(lines)


async def _send_active_player(bot, chat_id: int, auction_run_id: int) -> None:
    """Select the next player and send the live auction announcement."""
    async with AsyncSessionLocal() as session:
        service = AuctionService(session)
        run = await session.get(AuctionRun, auction_run_id)
        if run is None:
            return

        # Check runtime state before sending
        state = AuctionRuntime.get(auction_run_id)
        if state is None or state.paused or state.stopped:
            return

        player_row = await service.prepare_next_player(run)
        if player_row is None:
            await service.complete_auction_run(run)
            await session.commit()
            AuctionRuntime.remove(auction_run_id)
            await bot.send_message(
                chat_id,
                f"✅ Set {run.set_number} is complete. No eligible players remain.",
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
    markup = auction_keyboard(
        Decimal(str(tournament.minimum_bid_increment_cr)),
        is_admin=True,
    )

    # Send with photo if available
    if player.telegram_file_id:
        try:
            sent = await bot.send_photo(chat_id, player.telegram_file_id, caption=text, reply_markup=markup)
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
        from aiogram.types import BufferedInputFile

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
                result_text = f"UNSOLD -- {player.name}"
                team = None
            else:
                team = await session.get(Team, row.current_team_id)
                await service.complete_player_sold(
                    row, team, Decimal(str(row.current_bid_cr))
                )
                result_text = f"SOLD -- {player.name} to {team.name} for Rs.{row.current_bid_cr:.2f} Cr"
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
        await asyncio.sleep(5)

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

        # 10 seconds left
        if AuctionRuntime.get(auction_run_id) is not state:
            return
        once_path = os.path.join("data", "once.gif")
        if os.path.exists(once_path):
            await bot.send_animation(chat_id, FSInputFile(once_path), caption="GOING ONCE -- Place your bid now!")
        else:
            await bot.send_message(chat_id, "GOING ONCE -- Place your bid now!")
        await asyncio.sleep(5)

        # 5 seconds left
        if AuctionRuntime.get(auction_run_id) is not state:
            return
        twice_path = os.path.join("data", "twice.gif")
        if os.path.exists(twice_path):
            await bot.send_animation(chat_id, FSInputFile(twice_path), caption="GOING TWICE -- Last chance!")
        else:
            await bot.send_message(chat_id, "GOING TWICE -- Last chance!")
        await asyncio.sleep(5)

        # 0 seconds -- finalize
        if AuctionRuntime.get(auction_run_id) is not state:
            return

        await _finalize_player(bot, chat_id, auction_run_id)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Sold warning failed for auction_run_id=%s", auction_run_id)
        return


async def _on_timer_expired(bot, chat_id: int, auction_run_id: int) -> None:
    """Normal timer expired -- check if bids exist, then finalize or warn."""
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
        # No bids at all -- mark UNSOLD immediately
        await _finalize_player(bot, chat_id, auction_run_id)


@router.message(Command("start_auction"), AdminFilter())
async def start_auction_command(message: Message, state: FSMContext) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return

    await state.clear()

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("❌ No tournament configured for this group.")
            return

        # Check for active auction
        if await AuctionService(session).get_running_auction(tournament.id):
            await message.answer("⚠️ Auction already running. Stop it first.")
            return

        # Get distinct set numbers from players
        result = await session.execute(
            select(Player.set_number).distinct().order_by(Player.set_number)
        )
        set_numbers = [row[0] for row in result.all()]

    if not set_numbers:
        await message.answer("❌ No players loaded. Import players first.")
        return

    await state.set_state(AuctionStates.choosing_set_number)
    await message.answer(
        "🏆 Select the set to auction:",
        reply_markup=set_selection_keyboard(set_numbers),
    )


@router.callback_query(F.data == "auction:cancel_start")
async def auction_cancel_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Auction cancelled.")
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
    category = parts[2]  # "pending" or "unsold"
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

    # auction:timer:{set_number}:{category}:{secs}
    # or auction:timer:custom:{set_number}:{category}
    if parts[2] == "custom":
        set_number = int(parts[3])
        category = parts[4]
        await state.update_data(set_number=set_number, category=category)
        await callback.message.edit_text(
            "⏱️ Enter bid timer in seconds (1-600):"
        )
        await callback.answer()
        return

    set_number = int(parts[2])
    category = parts[3]
    bid_timer = int(parts[4])

    await _start_auction_with_params(callback, state, set_number, category, bid_timer)


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

    await message.delete()
    await _start_auction_with_params_msg(message, state, set_number, category, seconds)


async def _start_auction_with_params(callback, state, set_number, category, bid_timer):
    chat_id = callback.message.chat.id

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(chat_id)
        if not tournament:
            await callback.answer("No tournament found.", show_alert=True)
            return

        service = AuctionService(session)
        if await service.get_running_auction(tournament.id):
            await callback.answer("An auction is already running.", show_alert=True)
            return

        run = await service.create_auction_run(tournament.id, set_number, bid_timer)
        await service.start_auction_run(run)
        await session.commit()

    await state.clear()
    AuctionRuntime.create(run.id, chat_id, bid_timer)

    await callback.message.edit_text(
        f"✅ Auction started -- Set {set_number} | {category.title()} | Timer: {bid_timer}s"
    )
    await callback.answer()
    await _send_active_player(callback.message.bot, chat_id, run.id)


async def _start_auction_with_params_msg(message, state, set_number, category, bid_timer):
    chat_id = message.chat.id

    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(chat_id)
        if not tournament:
            await message.answer("No tournament found.")
            return

        service = AuctionService(session)
        if await service.get_running_auction(tournament.id):
            await message.answer("An auction is already running.")
            return

        run = await service.create_auction_run(tournament.id, set_number, bid_timer)
        await service.start_auction_run(run)
        await session.commit()

    await state.clear()
    AuctionRuntime.create(run.id, chat_id, bid_timer)

    await message.answer(
        f"✅ Auction started -- Set {set_number} | {category.title()} | Timer: {bid_timer}s"
    )
    await _send_active_player(message.bot, chat_id, run.id)


# ── admin controls ────────────────────────────────────────────────

async def _control(message: Message, action: str) -> str:
    try:
        async with AsyncSessionLocal() as session:
            tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
            if not tournament:
                return "❌ No tournament configured for this group."
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
                return "❌ No matching auction run found."

            if action == "pause":
                await service.pause_auction_run(run)
                state = AuctionRuntime.get(run.id)
                if state:
                    state.paused = True
                    AuctionRuntime.cancel_timer(state)
                    AuctionRuntime.cancel_last_call(state)
                text = "⏸️ Auction paused."

            elif action == "resume":
                await service.resume_auction_run(run)
                state = AuctionRuntime.get(run.id)
                if state:
                    state.paused = False
                    state.stopped = False
                text = "▶️ Auction resumed."

            else:
                await service.stop_auction_run(run)
                state = AuctionRuntime.get(run.id)
                if state:
                    state.stopped = True
                    state.paused = False
                    AuctionRuntime.cancel_timer(state)
                    AuctionRuntime.cancel_last_call(state)
                text = "⏹️ Auction stopped."

            await session.commit()
        return text
    except ValueError as exc:
        return str(exc)


@router.message(Command("pause_auction"), AdminFilter())
async def pause_auction(message: Message) -> None:
    await message.answer(await _control(message, "pause"))


@router.message(Command("resume_auction"), AdminFilter())
async def resume_auction(message: Message) -> None:
    await message.answer(await _control(message, "resume"))


@router.message(Command("stop_auction"), AdminFilter())
async def stop_auction(message: Message) -> None:
    await message.answer(await _control(message, "stop"))


@router.message(Command("status"), AdminFilter())
async def auction_status(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            await message.answer("❌ No tournament configured for this group.")
            return
        run = await AuctionService(session).get_running_auction(tournament.id)
        active = await AuctionService(session).get_active_auction_player(tournament.id) if run else None
    if not run:
        await message.answer("ℹ️ No auction is currently running.")
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

@router.callback_query(F.data == "auction:pause")
async def auction_pause_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    result = await _control(callback.message, "pause")
    await callback.answer(result, show_alert=True)


@router.callback_query(F.data == "auction:resume")
async def auction_resume_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    result = await _control(callback.message, "resume")
    await callback.answer(result, show_alert=True)


@router.callback_query(F.data == "auction:stop")
async def auction_stop_button(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    result = await _control(callback.message, "stop")
    await callback.answer(result, show_alert=True)


@router.callback_query(F.data == "auction:refresh")
async def auction_refresh(callback: CallbackQuery) -> None:
    await callback.answer("🔄 Info refreshes when a bid is placed.")


# ── bidding ───────────────────────────────────────────────────────

async def _button_bid(message: Message, user_id: int, amount: Decimal | None, increment: Decimal | None = None) -> str:
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if not tournament:
            return "\u274c No tournament configured."
        service = AuctionService(session)
        team = await service.get_team_by_owner(user_id, tournament.id)
        active = await service.get_active_auction_player(tournament.id)
        if not team or not active:
            return "\u274c You need to be a team owner with an active player."
        player = active.player

        # Same bidder check - can't bid on own highest bid
        if active.current_team_id and active.current_team_id == team.id:
            return "\u26a0\ufe0f You already have the highest bid!"

        bid = amount
        if bid is None:
            current = Decimal(str(active.current_bid_cr)) if active.current_bid_cr is not None else Decimal(str(player.base_price_cr))
            bid = current + increment
            if active.current_bid_cr is None:
                bid = max(Decimal(str(player.base_price_cr)), bid)
        try:
            await service.place_bid(active, team, tournament, bid, Decimal(str(tournament.minimum_bid_increment_cr)), user_id)
        except BidValidationError as exc:
            await session.rollback()
            return str(exc)
        await session.commit()

        # Update the live message with new bid info
        runtime = AuctionRuntime.get(active.auction_run_id)
        if runtime and runtime.live_message_id:
            try:
                text = _live_text(
                    player, team, bid, runtime.bid_timer_seconds,
                    bidder_username=team.owner_username,
                )
                markup = auction_keyboard(
                    Decimal(str(tournament.minimum_bid_increment_cr)),
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
                    await message.bot.edit_message_text(
                        text=text,
                        chat_id=message.chat.id,
                        message_id=runtime.live_message_id,
                        reply_markup=markup,
                    )
            except Exception:
                pass

    runtime = AuctionRuntime.get(active.auction_run_id)
    if runtime:
        await AuctionRuntime.restart_timer(runtime)

    # Return bid announcement message
    owner_display = f"@{team.owner_username}" if team.owner_username else "Owner"
    return f"\U0001f528 {team.name} ({team.short_code}) \u2192 Rs.{bid:.2f} Cr\nOwner: {owner_display}\nPlayer: {player.name}"


@router.callback_query(F.data.startswith("auction:bid_increment:"))
async def auction_increment_bid(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    increment = Decimal(callback.data.rsplit(":", 1)[-1])
    result = await _button_bid(callback.message, callback.from_user.id, None, increment)
    await callback.answer(
        result,
        show_alert=result.startswith("No ") or result.startswith("You ") or "must" in result,
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
        await message.answer("❌ Enter a positive amount (e.g. 4.70).")
        return
    result = await _button_bid(message, message.from_user.id, amount)
    await state.clear()
    if result.startswith("Bid accepted"):
        await message.answer(result)
    else:
        await message.answer(result)
