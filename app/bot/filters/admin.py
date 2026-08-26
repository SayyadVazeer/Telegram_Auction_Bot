from aiogram.types import TelegramObject
from aiogram.filters import BaseFilter

from app.config.settings import settings


def get_admin_ids() -> set[int]:
    if not settings.admin_ids.strip():
        return set()

    return {
        int(admin_id.strip())
        for admin_id in settings.admin_ids.split(",")
        if admin_id.strip()
    }


class AdminFilter(BaseFilter):
    async def __call__(
        self,
        event: TelegramObject,
    ) -> bool:
        user = getattr(event, "from_user", None)

        if user is None:
            return False

        return user.id in get_admin_ids()
