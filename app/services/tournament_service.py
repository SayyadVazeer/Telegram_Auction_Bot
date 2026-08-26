from sqlalchemy import select
from app.database.models.tournament import Tournament

async def get_by_telegram_chat_id(
    self,
    telegram_chat_id: int,
) -> Tournament | None:
    result = await self.session.execute(
        select(Tournament).where(
            Tournament.telegram_chat_id == telegram_chat_id,
        )
    )

    return result.scalar_one_or_none()
