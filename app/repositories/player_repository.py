from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.player import Player


async def get_available_set_numbers(
    session: AsyncSession,
) -> list[int]:
    result = await session.execute(
        select(Player.set_number)
        .distinct()
        .order_by(Player.set_number)
    )

    return list(result.scalars().all())
