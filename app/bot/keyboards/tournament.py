from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def tournament_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Create",
                    callback_data="tournament:create",
                ),
                InlineKeyboardButton(
                    text="✏️ Edit",
                    callback_data="tournament:edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="tournament:cancel",
                ),
            ],
        ]
    )


def tournament_edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Name",
                    callback_data="tournament:edit:name",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Team Purse",
                    callback_data="tournament:edit:purse",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Max Overseas",
                    callback_data="tournament:edit:overseas",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Max Players",
                    callback_data="tournament:edit:max_players",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Bid Increment",
                    callback_data="tournament:edit:increment",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Back",
                    callback_data="tournament:edit:back",
                ),
        ],
    ])
