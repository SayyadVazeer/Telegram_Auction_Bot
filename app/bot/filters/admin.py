from aiogram.types import TelegramObject
from aiogram.filters import BaseFilter

from app.services.admin_service import get_admin_ids


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in get_admin_ids()


class AdminFilter(BaseFilter):
    async def __call__(
        self,
        event: TelegramObject,
    ) -> bool:
        user = getattr(event, "from_user", None)

        if user is None:
            return False

        return user.id in get_admin_ids()
