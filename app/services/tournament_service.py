from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tournament import Tournament
from app.repositories.tournament_repository import (
    get_tournament_by_chat_id,
)


class TournamentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_chat_id(
        self,
        telegram_chat_id: int,
    ) -> Tournament | None:
        return await get_tournament_by_chat_id(
            self.session,
            telegram_chat_id,
        )