import os
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.services.auction_service import (
    AuctionService,
    BidValidationError,
)
from app.services.tournament_service import TournamentService
from app.services.auction_runtime import AuctionRuntime
from app.database.models.auction import AuctionRun


router = Router()


@router.message(Command("bid", "b"))
async def place_bid_command(message: Message) -> None:

    if message.from_user is None:
        return

    parts = message.text.split(maxsplit=1) if message.text else []

    # ── Auto-bid: no amount given → bid current + minimum increment ──
    auto_bid = len(parts) < 2 or not parts[1].strip()

    if auto_bid:
        # Calculate auto-bid amount
        async with AsyncSessionLocal() as session:
            service = AuctionService(session)
            tournament_service = TournamentService(session)
            tournament = await tournament_service.get_by_telegram_chat_id(message.chat.id)
            if not tournament:
                await message.answer("No tournament configured.")
                return
            auction_player = await service.get_active_auction_player(tournament.id)
            if not auction_player:
                await message.answer("No active player being auctioned.")
                return
            # Get minimum increment
            auction_run = await session.get(AuctionRun, auction_player.auction_run_id)
            min_inc = Decimal(str(auction_run.minimum_bid_increment_cr)) if auction_run else Decimal("0.25")
            # Get current highest bid (base_price is on Player, not AuctionPlayer)
            base = Decimal(str(auction_player.player.base_price_cr)) if auction_player.player else Decimal("0.25")
            current = Decimal(str(auction_player.current_bid_cr)) if auction_player.current_bid_cr else base
            bid_cr = current + min_inc
    else:
        bid_text = parts[1].strip()
        try:
            bid_cr = Decimal(bid_text)
        except InvalidOperation:
            await message.answer(
                "Invalid bid amount.\n\n"
                "Use an amount in Cr, for example:\n"
                "/bid 4\n"
                "/bid 4.7"
            )
            return

    if bid_cr <= Decimal("0"):
        await message.answer(
            "Bid must be greater than Rs.0 Cr."
        )
        return

    async with AsyncSessionLocal() as session:
        service = AuctionService(session)
        tournament_service = TournamentService(session)

        tournament = (
            await tournament_service.get_by_telegram_chat_id(
                message.chat.id
            )
        )

        if tournament is None:
            await message.answer(
                "No tournament is configured for this group."
            )
            return

        # Check auction state first
        run = await service.get_running_auction(tournament.id)
        if not run:
            await message.answer("Auction is not running.")
            return
        rt = AuctionRuntime.get(run.id)
        if rt and rt.paused:
            await message.answer("⏸️ Auction is paused. Bidding is not allowed.")
            return
        if rt and rt.stopped:
            await message.answer("⏹️ Auction is stopped. Bidding is not allowed.")
            return

        team = await service.get_team_by_owner(
            telegram_user_id=message.from_user.id,
            tournament_id=tournament.id,
        )

        if team is None:
            await message.answer(
                "You are not registered as a team owner."
            )
            return

        auction_player = (
            await service.get_active_auction_player(
                tournament.id
            )
        )

        if auction_player is None:
            await message.answer(
                "No active player being auctioned."
            )
            return

        if auction_player.current_team_id and auction_player.current_team_id == team.id:
            await message.answer("You already have the highest bid!")
            return

        # Check overseas limit
        from app.database.models.player import Player
        from app.database.models.auction import AuctionResult
        player_obj = await session.get(Player, auction_player.player_id)
        if player_obj and player_obj.is_overseas:
            from sqlalchemy import func as sa_func
            ovr_result = await session.execute(
                select(sa_func.count(AuctionResult.id))
                .join(Player, Player.id == AuctionResult.player_id)
                .where(
                    AuctionResult.tournament_id == tournament.id,
                    AuctionResult.winning_team_id == team.id,
                    AuctionResult.result_status == "SOLD",
                    Player.is_overseas == True,
                )
            )
            overseas_count = int(ovr_result.scalar() or 0)
            if overseas_count >= tournament.max_overseas_players:
                await message.answer(f"❌ Overseas limit reached! {team.name} already has {overseas_count}/{tournament.max_overseas_players} overseas players.")
                return

        # Check max players
        from sqlalchemy import func as sa_func
        count_result = await session.execute(
            select(sa_func.count(AuctionResult.id)).where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == "SOLD",
            )
        )
        team_player_count = int(count_result.scalar() or 0)
        if team_player_count >= tournament.max_players_per_team:
            await message.answer(f"❌ Team full! {team.name} already has {team_player_count}/{tournament.max_players_per_team} players.")
            return

        # Check purse
        spent_result = await session.execute(
            select(sa_func.coalesce(sa_func.sum(AuctionResult.final_bid_cr), 0)).where(
                AuctionResult.tournament_id == tournament.id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == "SOLD",
            )
        )
        spent = Decimal(str(spent_result.scalar() or 0))
        spent += Decimal(str(team.purse_adjustment_cr or 0))
        remaining = Decimal(str(tournament.purse_cr)) - spent
        if bid_cr > remaining:
            await message.answer(f"❌ Insufficient purse! {team.name} has Rs.{remaining:.2f} Cr remaining, bid is Rs.{bid_cr:.2f} Cr.")
            return

        auction_run = await session.get(AuctionRun, auction_player.auction_run_id)
        run_min_inc = Decimal(str(auction_run.minimum_bid_increment_cr)) if auction_run else Decimal("0.25")

        try:
            await service.place_bid(
                auction_player=auction_player,
                team=team,
                tournament=tournament,
                bid_cr=bid_cr,
                minimum_increment_cr=run_min_inc,
                bidder_telegram_id=message.from_user.id,
            )

            await session.commit()

            runtime = AuctionRuntime.get(auction_player.auction_run_id)
            if runtime and runtime.live_message_id:
                try:
                    from app.bot.handlers.auction import _live_text
                    from app.bot.keyboards.auction import auction_keyboard as ak
                    text = _live_text(
                        auction_player.player, team, bid_cr, runtime.bid_timer_seconds,
                        bidder_username=team.owner_username,
                    )
                    markup = ak(
                        run_min_inc,
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

            if runtime is not None:
                await AuctionRuntime.restart_timer(runtime)

        except BidValidationError as exc:
            await session.rollback()
            await message.answer(f"{exc}")
            return

        owner_username = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else "Owner"
        )

        bid_msg = (
            f"🔨 BID\n\n"
            f"💰 Current Highest Bid: Rs.{bid_cr:.2f} Cr\n"
            f"🏏 Player: {auction_player.player.name}\n"
            f"🎯 Role: {auction_player.player.role}\n"
            f"🏏 Team Name: {team.name} ({team.short_code})\n"
            f"🧑 Bid by: {owner_username}\n\n"
            "Do I hear anyone else?"
        )
        # Rotate through bid1, bid2, bid3 (per-auction counter)
        if runtime:
            runtime.bid_counter += 1
            bid_num = (runtime.bid_counter % 4) + 1
        else:
            bid_num = 1
        
        # Use file_id from auction module
        from app.bot.handlers.auction import _send_media
        bid_thread_id = runtime.thread_id if runtime else None
        await _send_media(
            message.bot, message.chat.id,
            f"bid{bid_num}", os.path.join("data", f"bid{bid_num}.gif"),
            caption=bid_msg,
            thread_id=bid_thread_id,
        )
