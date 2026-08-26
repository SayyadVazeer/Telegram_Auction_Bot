import asyncio
import logging

from app.bot.bot import bot, dp
from app.bot.handlers import start_router


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    dp.include_router(start_router)

    await bot.delete_webhook(drop_pending_updates=True)

    print("Telegram Auction Bot is starting...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
