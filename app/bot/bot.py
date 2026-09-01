from aiogram import Bot, Dispatcher

from app.config.settings import settings

from app.bot.handlers.tournament import router as tournament_router
from app.bot.handlers.team import router as team_router
from app.bot.handlers.bidding import router as bidding_router
from app.bot.handlers.auction import router as auction_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.players_admin import router as players_admin_router
from app.bot.handlers.simulate import router as simulate_router

bot = Bot(token=settings.bot_token)

dp = Dispatcher()

dp.include_router(tournament_router)
dp.include_router(team_router)
dp.include_router(bidding_router)
dp.include_router(auction_router)
dp.include_router(start_router)
dp.include_router(players_admin_router)
dp.include_router(simulate_router)

# Register commands with Telegram
async def register_commands():
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        # ── Everyone ──
        BotCommand(command="start", description="🏠 Open main menu"),
        BotCommand(command="help", description="📖 Show all available commands"),
        BotCommand(command="cancel", description="❌ Cancel current operation"),
        BotCommand(command="teams", description="🏏 View all teams"),
        BotCommand(command="my_team", description="👥 View your team roster & purse"),
        BotCommand(command="purse", description="💰 Check your team purse"),
        BotCommand(command="team_logo", description="🖼️ Upload your team logo"),
        BotCommand(command="bid", description="💰 Place a bid (e.g. /bid 4.70)"),
        BotCommand(command="b", description="💰 Short form of /bid"),
        BotCommand(command="trade_player", description="🔄 Trade a player with another team"),
        BotCommand(command="accept_trade", description="✅ Accept a trade proposal"),
        BotCommand(command="reject_trade", description="🚫 Reject a trade proposal"),
        BotCommand(command="add_coowner", description="👤 Add co-owner to your team"),
        BotCommand(command="remove_coowner", description="👤 Remove co-owner from your team"),
        BotCommand(command="player_photo", description="📸 View a player's photo"),
        # ── Admin ──
        BotCommand(command="create_tournament", description="🏆 Create a new tournament"),
        BotCommand(command="complete_tournament", description="❌ Complete/delete tournament"),
        BotCommand(command="add_player", description="➕ Add a new player"),
        BotCommand(command="add_team", description="➕ Add a new team"),
        BotCommand(command="assign_owner", description="👤 Assign owner to a team"),
        BotCommand(command="edit_team", description="✏️ Edit team name or code"),
        BotCommand(command="delete_team", description="🗑️ Delete a team"),
        BotCommand(command="remove_owner", description="👤 Remove team owner"),
        BotCommand(command="start_auction", description="🔴 Start auction for a set"),
        BotCommand(command="pause_auction", description="⏸️ Pause running auction"),
        BotCommand(command="resume_auction", description="▶️ Resume paused auction"),
        BotCommand(command="stop_auction", description="⏹️ Stop running auction"),
        BotCommand(command="next_player", description="⏭️ Skip to next player"),
        BotCommand(command="status", description="ℹ️ View auction status"),
        BotCommand(command="manual_sell", description="💰 Manually sell player to team"),
        BotCommand(command="manual_unsell", description="💸 Remove player from team"),
        BotCommand(command="trade_on", description="🔄 Enable player trading"),
        BotCommand(command="trade_off", description="🔄 Disable player trading"),
        # ── Simulation ──
        BotCommand(command="simulate_match", description="🏏 Simulate a match between two teams"),
        BotCommand(command="tournament_table", description="📊 View tournament standings"),
        BotCommand(command="match_history", description="📋 View past matches"),
        BotCommand(command="refresh_stats", description="🔄 Refresh player stats from internet"),
        BotCommand(command="import_stats", description="📥 Import player stats from CSV"),
        BotCommand(command="update_tournament_stats", description="📈 Merge auction results into player stats"),
    ])
