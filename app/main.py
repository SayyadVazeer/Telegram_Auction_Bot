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




async def _ensure_max_bid_column():
    """Add bid increment columns to auction_runs, drop from tournaments if present."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            # Add columns to auction_runs
            await session.execute(text(
                "ALTER TABLE auction_runs ADD COLUMN IF NOT EXISTS minimum_bid_increment_cr NUMERIC(12,2) DEFAULT 0.25"
            ))
            await session.execute(text(
                "ALTER TABLE auction_runs ADD COLUMN IF NOT EXISTS maximum_bid_increment_cr NUMERIC(12,2)"
            ))
            # Drop from tournaments if present
            try:
                await session.execute(text(
                    "ALTER TABLE tournaments DROP COLUMN IF EXISTS minimum_bid_increment_cr"
                ))
            except Exception:
                pass
            try:
                await session.execute(text(
                    "ALTER TABLE tournaments DROP COLUMN IF EXISTS maximum_bid_increment_cr"
                ))
            except Exception:
                pass
            await session.commit()
        logging.info("Ensured auction_runs has min/max bid increment columns")
    except Exception as e:
        logging.warning("Could not update bid columns: %s", e)


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

async def _fix_auction_results_nullable():
    """Make auction_run_id and auction_player_id nullable in auction_results."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text(
                "ALTER TABLE auction_results ALTER COLUMN auction_run_id DROP NOT NULL"
            ))
            await session.execute(text(
                "ALTER TABLE auction_results ALTER COLUMN auction_player_id DROP NOT NULL"
            ))
            await session.commit()
        logging.info("Made auction_run_id and auction_player_id nullable in auction_results")
    except Exception as e:
        logging.warning("Could not update auction_results columns: %s", e)


async def _ensure_coowner_columns():
    """Add co_owner columns to teams table."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text(
                "ALTER TABLE teams ADD COLUMN IF NOT EXISTS co_owner_telegram_id BIGINT"
            ))
            await session.execute(text(
                "ALTER TABLE teams ADD COLUMN IF NOT EXISTS co_owner_username VARCHAR(100)"
            ))
            await session.commit()
        logging.info("Ensured co_owner columns in teams table")
    except Exception as e:
        logging.warning("Could not update co_owner columns: %s", e)

async def _ensure_media_files_table():
    """Create media_files table if it doesn't exist, add missing columns."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            # Create table if not exists
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS media_files (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(32) UNIQUE NOT NULL,
                    telegram_file_id VARCHAR(512) NOT NULL,
                    telegram_unique_id VARCHAR(128),
                    local_path VARCHAR(256),
                    media_type VARCHAR(16) NOT NULL DEFAULT 'animation',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP
                )
            """))
            # Add any missing columns (in case table existed with different schema)
            for col_def in [
                "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS telegram_unique_id VARCHAR(128)",
                "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS local_path VARCHAR(256)",
                "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS media_type VARCHAR(16) DEFAULT 'animation'",
                "ALTER TABLE media_files ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
            ]:
                try:
                    await session.execute(text(col_def))
                except Exception:
                    pass
            await session.commit()
        logging.info("Ensured media_files table exists")
    except Exception as e:
        logging.warning("Could not create media_files table: %s", e)

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Run migrations FIRST (before any queries)
    await _ensure_max_bid_column()
    await _fix_photo_paths()
    await _fix_auction_results_nullable()
    await _ensure_coowner_columns()
    await _ensure_media_files_table()

    # Recover orphaned auctions from previous runs
    await _recover_orphaned_auctions()

    # Register bot commands with Telegram
    try:
        from app.bot.bot import register_commands
        await register_commands()
    except Exception as e:
        logging.warning("Could not register commands: %s", e)

    await bot.delete_webhook(drop_pending_updates=True)

    print("Telegram Auction Bot is starting...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
