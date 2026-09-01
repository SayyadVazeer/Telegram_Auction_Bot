"""Match simulation Telegram handlers — V2 Coming Soon."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

COMING_SOON = (
    "🚧 This feature is coming in V2!\n\n"
    "⚔️ Match Simulation\n"
    "📊 Tournament Table\n"
    "📋 Match History\n"
    "🃏 Scorecard\n"
    "🔄 Player Stats\n\n"
    "Stay Tuned! 🏏"
)


@router.message(Command("simulate_match"))
async def simulate_match(message: Message) -> None:
    await message.answer(COMING_SOON)


@router.message(Command("tournament_table"))
async def tournament_table(message: Message) -> None:
    await message.answer(COMING_SOON)


@router.message(Command("match_history"))
async def match_history(message: Message) -> None:
    await message.answer(COMING_SOON)


@router.message(Command("view_scorecard"))
async def view_scorecard(message: Message) -> None:
    await message.answer(COMING_SOON)


@router.message(Command("refresh_stats"))
async def refresh_stats(message: Message) -> None:
    await message.answer(COMING_SOON)


@router.message(Command("import_stats"))
async def import_stats(message: Message) -> None:
    await message.answer(COMING_SOON)


@router.message(Command("update_tournament_stats"))
async def update_tournament_stats(message: Message) -> None:
    await message.answer(COMING_SOON)
