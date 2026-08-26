from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def team_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Create",
                    callback_data="team:create",
                ),
                InlineKeyboardButton(
                    text="✏️ Edit",
                    callback_data="team:edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="team:cancel",
                ),
            ],
        ]
    )


def team_edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Team Name",
                    callback_data="team:edit:name",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Short Code",
                    callback_data="team:edit:short_code",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Back",
                    callback_data="team:edit:back",
                ),
            ],
        ]
    )

def team_list_keyboard(
    teams,
) -> InlineKeyboardMarkup:
    buttons = []

    for team in teams:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🏏 {team.short_code} — {team.name}",
                    callback_data=f"team:view:{team.id}",
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )
