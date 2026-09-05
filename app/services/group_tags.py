"""Custom admin-title tags for team owners/co-owners in the tournament group.

Telegram cannot rename regular members; the only way to show a label next to a
name (e.g. "CSK", "CSK Co") is a custom admin title, which requires the user to
be a group administrator. We promote the user with no real moderation rights
(only the ability to invite, needed to make promoteChatMember actually promote)
and set the title. On removal we demote ONLY if the user's current custom title
matches the one we set, so pre-existing admins are never stripped of rights.
"""

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

logger = logging.getLogger(__name__)

# Every boolean right off — passing this to promote_chat_member demotes.
_DEMOTE_RIGHTS = dict(
    is_anonymous=False,
    can_manage_chat=False,
    can_change_info=False,
    can_delete_messages=False,
    can_invite_users=False,
    can_restrict_members=False,
    can_pin_messages=False,
    can_promote_members=False,
    can_manage_video_chats=False,
    can_manage_topics=False,
)


def owner_title(code: str) -> str:
    return code[:16]


def co_owner_title(code: str) -> str:
    return f"{code} Co"[:16]


async def set_group_tag(bot: Bot, chat_id: int, user_id: int, title: str) -> None:
    """Promote the user (no moderation rights) and set their custom title.

    Best-effort: failures (e.g. the bot is not an admin with promote rights,
    or the target is an admin the bot did not promote) are logged, not raised.
    """
    promote_rights = dict(_DEMOTE_RIGHTS)
    promote_rights["can_invite_users"] = True  # promoteChatMember with all
    # False demotes, so one harmless right is needed to promote.
    try:
        await bot.promote_chat_member(chat_id, user_id, **promote_rights)
    except Exception as exc:
        logger.warning("Promote user %s in chat %s failed: %s", user_id, chat_id, exc)
    try:
        await bot.set_chat_administrator_custom_title(chat_id, user_id, title)
    except Exception as exc:
        logger.warning("Set title %r for user %s in chat %s failed: %s", title, user_id, chat_id, exc)


async def clear_group_tag(bot: Bot, chat_id: int, user_id: int, expected_title: str) -> None:
    """Demote the user only if their current custom title matches expected_title.

    Prevents us from stripping admin rights from a real pre-existing admin
    whose title is different from the team tag we assigned.
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return
        if getattr(member, "custom_title", None) != expected_title:
            return
        await bot.promote_chat_member(chat_id, user_id, **_DEMOTE_RIGHTS)
    except Exception as exc:
        logger.warning("Clear tag for user %s in chat %s failed: %s", user_id, chat_id, exc)
