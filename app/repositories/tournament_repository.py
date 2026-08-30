from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tournament import Tournament


async def get_tournament_by_chat_id(
    session: AsyncSession,
    chat_id: int,
) -> Tournament | None:
    result = await session.execute(
        select(Tournament).where(
            Tournament.telegram_chat_id == chat_id
        )
    )

    return result.scalar_one_or_none()


async def create_tournament(
    session: AsyncSession,
    *,
    telegram_chat_id: int,
    name: str,
    purse_cr: Decimal,
    max_overseas_players: int,
    max_players_per_team: int,
) -> Tournament:
    tournament = Tournament(
        telegram_chat_id=telegram_chat_id,
        name=name,
        purse_cr=purse_cr,
        max_overseas_players=max_overseas_players,
        max_players_per_team=max_players_per_team,
    )

    session.add(tournament)

    await session.flush()

    return tournament
