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

async def _ensure_purse_adjustment_column():
    """Add purse_adjustment_cr column to teams table."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text(
                "ALTER TABLE teams ADD COLUMN IF NOT EXISTS purse_adjustment_cr NUMERIC(12,2) NOT NULL DEFAULT 0"
            ))
            await session.commit()
        logging.info("Ensured purse_adjustment_cr column in teams table")
    except Exception as e:
        logging.warning("Could not update purse_adjustment column: %s", e)


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

async def _ensure_match_tables():
    """Create match simulation tables if they don't exist."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            # matches
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS matches (
                    id SERIAL PRIMARY KEY,
                    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
                    match_number INT DEFAULT 1,
                    team1_id INT REFERENCES teams(id) ON DELETE CASCADE,
                    team2_id INT REFERENCES teams(id) ON DELETE CASCADE,
                    venue_code VARCHAR(10) NOT NULL,
                    venue_name VARCHAR(150) NOT NULL,
                    toss_winner_id INT REFERENCES teams(id),
                    toss_decision VARCHAR(10),
                    result_type VARCHAR(30),
                    result_detail VARCHAR(200),
                    winner_team_id INT REFERENCES teams(id),
                    potm_player_id INT REFERENCES players(id),
                    potm_reason VARCHAR(200),
                    status VARCHAR(20) DEFAULT 'PENDING',
                    team1_setup TEXT,
                    team2_setup TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """))
            # match_innings
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS match_innings (
                    id SERIAL PRIMARY KEY,
                    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
                    innings_number INT NOT NULL,
                    batting_team_id INT REFERENCES teams(id),
                    bowling_team_id INT REFERENCES teams(id),
                    total_runs INT DEFAULT 0,
                    total_wickets INT DEFAULT 0,
                    total_balls INT DEFAULT 0,
                    extras_wides INT DEFAULT 0,
                    extras_noballs INT DEFAULT 0,
                    extras_byes INT DEFAULT 0,
                    extras_legbyes INT DEFAULT 0,
                    extras_total INT DEFAULT 0,
                    run_rate NUMERIC(5,2) DEFAULT 0
                )
            """))
            # match_deliveries
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS match_deliveries (
                    id SERIAL PRIMARY KEY,
                    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
                    innings_number INT NOT NULL,
                    ball_number INT NOT NULL,
                    over_number INT NOT NULL,
                    ball_in_over INT NOT NULL,
                    striker_id INT REFERENCES players(id),
                    non_striker_id INT REFERENCES players(id),
                    bowler_id INT REFERENCES players(id),
                    outcome VARCHAR(20) NOT NULL,
                    runs_scored INT DEFAULT 0,
                    extras INT DEFAULT 0,
                    total_runs INT DEFAULT 0,
                    is_wicket BOOLEAN DEFAULT FALSE,
                    dismissal_type VARCHAR(30),
                    dismissal_detail VARCHAR(200),
                    dismissed_player_id INT REFERENCES players(id),
                    fielder_id INT REFERENCES players(id),
                    commentary TEXT
                )
            """))
            # match_batting_scorecard
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS match_batting_scorecard (
                    id SERIAL PRIMARY KEY,
                    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
                    innings_number INT NOT NULL,
                    player_id INT REFERENCES players(id),
                    team_id INT REFERENCES teams(id),
                    batting_order INT DEFAULT 0,
                    runs INT DEFAULT 0,
                    balls INT DEFAULT 0,
                    fours INT DEFAULT 0,
                    sixes INT DEFAULT 0,
                    is_not_out BOOLEAN DEFAULT FALSE,
                    dismissal_type VARCHAR(30),
                    dismissed_by_id INT REFERENCES players(id),
                    strike_rate NUMERIC(6,2) DEFAULT 0
                )
            """))
            # match_bowling_scorecard
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS match_bowling_scorecard (
                    id SERIAL PRIMARY KEY,
                    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
                    innings_number INT NOT NULL,
                    player_id INT REFERENCES players(id),
                    team_id INT REFERENCES teams(id),
                    balls_bowled INT DEFAULT 0,
                    runs_conceded INT DEFAULT 0,
                    wickets INT DEFAULT 0,
                    wides INT DEFAULT 0,
                    noballs INT DEFAULT 0,
                    economy NUMERIC(5,2) DEFAULT 0
                )
            """))
            # tournament_standings
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS tournament_standings (
                    id SERIAL PRIMARY KEY,
                    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
                    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
                    matches_played INT DEFAULT 0,
                    wins INT DEFAULT 0,
                    losses INT DEFAULT 0,
                    ties INT DEFAULT 0,
                    no_result INT DEFAULT 0,
                    runs_for INT DEFAULT 0,
                    balls_faced INT DEFAULT 0,
                    runs_against INT DEFAULT 0,
                    balls_bowled INT DEFAULT 0,
                    points INT DEFAULT 0,
                    nrr NUMERIC(6,3) DEFAULT 0.000,
                    UNIQUE(tournament_id, team_id)
                )
            """))
            await session.commit()
        logging.info("Ensured match simulation tables exist")
    except Exception as e:
        logging.warning("Could not create match tables: %s", e)


async def _ensure_player_stats_table():
    """Create player_stats table for cached scraped stats."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS player_stats (
                    id SERIAL PRIMARY KEY,
                    player_id VARCHAR(20) UNIQUE REFERENCES players(player_id),
                    bat_matches INT DEFAULT 0,
                    bat_innings INT DEFAULT 0,
                    bat_runs INT DEFAULT 0,
                    bat_highest INT DEFAULT 0,
                    bat_average NUMERIC(5,2) DEFAULT 0,
                    bat_strike_rate NUMERIC(5,2) DEFAULT 0,
                    bat_100s INT DEFAULT 0,
                    bat_50s INT DEFAULT 0,
                    bat_4s INT DEFAULT 0,
                    bat_6s INT DEFAULT 0,
                    bat_powerplay_sr NUMERIC(5,2),
                    bat_middle_sr NUMERIC(5,2),
                    bat_death_sr NUMERIC(5,2),
                    bat_vs_pace_avg NUMERIC(5,2),
                    bat_vs_spin_avg NUMERIC(5,2),
                    bowl_matches INT DEFAULT 0,
                    bowl_innings INT DEFAULT 0,
                    bowl_wickets INT DEFAULT 0,
                    bowl_average NUMERIC(5,2) DEFAULT 0,
                    bowl_economy NUMERIC(5,2) DEFAULT 0,
                    bowl_strike_rate NUMERIC(5,2) DEFAULT 0,
                    bowl_best VARCHAR(10),
                    bowl_powerplay_econ NUMERIC(5,2),
                    bowl_middle_econ NUMERIC(5,2),
                    bowl_death_econ NUMERIC(5,2),
                    catches INT DEFAULT 0,
                    run_outs INT DEFAULT 0,
                    stumpings INT DEFAULT 0,
                    bat_rating INT DEFAULT 0,
                    bowl_rating INT DEFAULT 0,
                    overall_rating INT DEFAULT 0,
                    power_rating INT DEFAULT 0,
                    timing_rating INT DEFAULT 0,
                    consistency_rating INT DEFAULT 0,
                    clutch_rating INT DEFAULT 0,
                    last_updated TIMESTAMP,
                    source VARCHAR(50)
                )
            """))
            await session.commit()
        logging.info("Ensured player_stats table exists")
    except Exception as e:
        logging.warning("Could not create player_stats table: %s", e)


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
    await _ensure_purse_adjustment_column()
    await _ensure_media_files_table()
    await _ensure_match_tables()
    await _ensure_player_stats_table()

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
