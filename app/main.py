import asyncio
import logging

from sqlalchemy import select, update

from app.bot.bot import bot, dp
from app.config.settings import settings
from app.database.session import AsyncSessionLocal
from app.database.models.auction import AuctionRun


async def _recover_orphaned_auctions():
    """On startup, mark any RUNNING/PAUSED auction runs as STOPPED."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AuctionRun).where(
                AuctionRun.status.in_(["RUNNING", "PAUSED"])
            )
        )
        orphaned = result.scalars().all()
        for run in orphaned:
            logging.info(
                "Recovering orphaned auction run %s (set %s, status %s)",
                run.id, run.set_number, run.status,
            )
            run.status = "STOPPED"
        if orphaned:
            await session.commit()
            logging.info("Recovered %d orphaned auction runs.", len(orphaned))




async def _fix_photo_paths():
    """Set telegram_photo_path for all players to use forward slashes."""
    import os
    from sqlalchemy import select, update
    from app.database.models.player import Player

    async with AsyncSessionLocal() as session:
        # First: fix any backslash paths to forward slashes
        result = await session.execute(select(Player))
        all_players = result.scalars().all()
        fixed = 0
        for p in all_players:
            if p.telegram_photo_path and chr(92) in p.telegram_photo_path:
                p.telegram_photo_path = p.telegram_photo_path.replace(chr(92), "/")
                fixed += 1
            # Also set path if NULL
            if not p.telegram_photo_path:
                p.telegram_photo_path = f"data/photos/{p.player_id}.jpg"
                fixed += 1
        if fixed:
            await session.commit()
            logging.info("Fixed %d photo paths (backslashes -> forward slashes).", fixed)

        # Log a sample
        result2 = await session.execute(select(Player).limit(3))
        for p in result2.scalars():
            exists = os.path.exists(p.telegram_photo_path) if p.telegram_photo_path else False
            logging.info("  Sample: %s -> %s (exists=%s)", p.player_id, p.telegram_photo_path, exists)
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Recover orphaned auctions from previous runs
    await _recover_orphaned_auctions()
    await _fix_photo_paths()

    await bot.delete_webhook(drop_pending_updates=True)

    print("Telegram Auction Bot is starting...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
