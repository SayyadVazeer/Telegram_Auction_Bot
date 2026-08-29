from aiogram import Bot, Dispatcher

from app.config.settings import settings

from app.bot.handlers.tournament import router as tournament_router
from app.bot.handlers.team import router as team_router
from app.bot.handlers.bidding import router as bidding_router
from app.bot.handlers.auction import router as auction_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.players_admin import router as players_admin_router

bot = Bot(token=settings.bot_token)

dp = Dispatcher()

dp.include_router(tournament_router)
dp.include_router(team_router)
dp.include_router(bidding_router)
dp.include_router(auction_router)
dp.include_router(start_router)
dp.include_router(players_admin_router)


