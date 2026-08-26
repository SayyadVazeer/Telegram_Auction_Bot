from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.filters.admin import AdminFilter


router = Router()


@router.message(Command("start"), AdminFilter())
async def admin_start_handler(message: Message):
    await message.answer(
        "🏏 Telegram Auction Bot\n\n"
        "✅ Admin access granted.\n\n"
        "The auction system is ready for configuration."
    )


@router.message(Command("start"))
async def user_start_handler(message: Message):
    await message.answer(
        "🏏 Telegram Auction Bot\n\n"
        "You are not authorized to access the admin panel."
    )
