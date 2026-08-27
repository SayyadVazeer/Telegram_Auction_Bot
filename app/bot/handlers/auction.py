from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.states.auction_states import AuctionStates
from app.database.session import AsyncSessionLocal
from app.services.auction_service import AuctionService
from app.services.tournament_service import TournamentService


router = Router()


@router.message(Command("start_auction"))
async def start_auction_command(
    message: Message,
    state: FSMContext,
) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(
            "⚠️ This command can only be used inside "
            "the tournament group."
        )
        return

    await state.clear()
    await state.set_state(
        AuctionStates.waiting_for_set_number
    )

    await message.answer(
        "🔴 Start Auction\n\n"
        "Enter the set number to auction.\n\n"
        "Example: 1"
    )


@router.message(AuctionStates.waiting_for_set_number)
async def auction_set_number(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    try:
        set_number = int(value)
    except ValueError:
        await message.answer(
            "❌ Please enter a valid set number.\n\n"
            "Example: 1"
        )
        return

    if set_number <= 0:
        await message.answer(
            "❌ Set number must be greater than zero."
        )
        return

    await state.update_data(
        set_number=set_number
    )

    await state.set_state(
        AuctionStates.waiting_for_bid_timer
    )

    await message.answer(
        "⏱️ Enter the bid timer in seconds.\n\n"
        "Example: 30"
    )


@router.message(AuctionStates.waiting_for_bid_timer)
async def auction_bid_timer(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    try:
        bid_timer_seconds = int(value)
    except ValueError:
        await message.answer(
            "❌ Please enter a valid number of seconds.\n\n"
            "Example: 30"
        )
        return

    if bid_timer_seconds <= 0:
        await message.answer(
            "❌ Bid timer must be greater than zero."
        )
        return

    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        tournament_service = TournamentService(session)

        tournament = (
            await tournament_service.get_by_telegram_chat_id(
                message.chat.id
            )
        )

        if tournament is None:
            await state.clear()

            await message.answer(
                "❌ No tournament is configured for this group."
            )
            return

        auction_service = AuctionService(session)

        running_auction = (
            await auction_service.get_running_auction(
                tournament.id
            )
        )

        if running_auction is not None:
            await message.answer(
                "❌ An auction is already running "
                "in this tournament."
            )
            return

        auction_run = await auction_service.create_auction_run(
            tournament_id=tournament.id,
            set_number=data["set_number"],
            bid_timer_seconds=bid_timer_seconds,
        )

        await auction_service.start_auction_run(
            auction_run
        )

        auction_player = (
            await auction_service.prepare_next_player(
                auction_run
            )
        )

        if auction_player is None:
            await session.rollback()

            await state.clear()

            await message.answer(
                "❌ No available players were found "
                f"in set {data['set_number']}."
            )
            return

        await auction_service.activate_player(
            auction_player
        )

        await session.commit()

    await state.clear()

    await message.answer(
        "✅ Auction started successfully!\n\n"
        f"Set: {data['set_number']}\n"
        f"Bid timer: {bid_timer_seconds} seconds\n\n"
        f"Player ID: {auction_player.player_id}"
    )
