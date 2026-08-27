from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.database.session import AsyncSessionLocal
from app.services.auction_service import (
    AuctionService,
    BidValidationError,
)
from app.services.tournament_service import TournamentService


router = Router()


@router.message(Command("bid", "b"))
async def place_bid_command(message: Message) -> None:

    if message.from_user is None:
        return

    parts = message.text.split(maxsplit=1) if message.text else []

    if len(parts) != 2:
        await message.answer(
            "❌ Please enter a bid amount.\n\n"
            "Examples:\n"
            "/bid 4.7\n"
            "/b 4.7"
        )
        return

    bid_text = parts[1].strip()

    try:
        bid_cr = Decimal(bid_text)
    except InvalidOperation:
        await message.answer(
            "❌ Invalid bid amount.\n\n"
            "Use an amount in Cr, for example:\n"
            "/bid 4\n"
            "/bid 4.7"
        )
        return

    if bid_cr <= Decimal("0"):
        await message.answer(
            "❌ Bid must be greater than ₹0 Cr."
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
                "❌ No tournament is configured for this group."
            )
            return

        team = await service.get_team_by_owner(
            telegram_user_id=message.from_user.id,
            tournament_id=tournament.id,
        )

        if team is None:
            await message.answer(
                "❌ You are not registered as a team owner."
            )
            return

        auction_player = (
            await service.get_active_auction_player(
                tournament.id
            )
        )

        if auction_player is None:
            await message.answer(
                "❌ There is currently no player accepting bids."
            )
            return

        try:
            await service.place_bid(
                auction_player=auction_player,
                team=team,
                tournament=tournament,
                bid_cr=bid_cr,
                minimum_increment_cr=Decimal(
                    str(tournament.minimum_bid_increment_cr)
                ),
                bidder_telegram_id=message.from_user.id,
            )

            await session.commit()

        except BidValidationError as exc:
            await session.rollback()

            await message.answer(
                f"❌ {exc}"
            )
            return

        owner_username = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else "Telegram Owner"
        )

        await message.answer(
            "🔨 BID\n\n"
            f"🏏 Team: {team.name} ({team.short_code})\n"
            f"💰 Bid: ₹{bid_cr:.2f} Cr\n"
            f"🤴 Owner: {owner_username}"
        )
