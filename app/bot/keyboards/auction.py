from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def auction_keyboard(
    minimum_increment: Decimal | None = None,
    *,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    increment = minimum_increment or Decimal("0.50")
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔨 BID +{increment:.2f}",
                callback_data=f"auction:bid_increment:{increment:.2f}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="✏️ Custom bid",
                callback_data="auction:custom_bid",
            ),
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data="auction:refresh",
            ),
        ],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⏸️ Pause",
                    callback_data="auction:pause",
                ),
                InlineKeyboardButton(
                    text="▶️ Resume",
                    callback_data="auction:resume",
                ),
                InlineKeyboardButton(
                    text="⏹️ Stop",
                    callback_data="auction:stop",
                ),
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def set_selection_keyboard(
    set_numbers: list[int],
) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(set_numbers), 4):
        chunk = set_numbers[i:i + 4]
        rows.append([
            InlineKeyboardButton(
                text=str(snum),
                callback_data=f"auction:set:{snum}",
            )
            for snum in chunk
        ])
    rows.append([
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data="auction:cancel_start",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_keyboard(
    set_number: int,
    pending_count: int,
    unsold_count: int,
) -> InlineKeyboardMarkup:
    rows = []
    if pending_count > 0:
        rows.append([
            InlineKeyboardButton(
                text=f"🟢 Pending ({pending_count})",
                callback_data=f"auction:cat:pending:{set_number}",
            )
        ])
    if unsold_count > 0:
        rows.append([
            InlineKeyboardButton(
                text=f"🟡 Unsold ({unsold_count})",
                callback_data=f"auction:cat:unsold:{set_number}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data="auction:cancel_start",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timer_keyboard(
    set_number: int,
    category: str,
) -> InlineKeyboardMarkup:
    rows = []
    for secs in [15, 20, 30, 45, 60]:
        rows.append([
            InlineKeyboardButton(
                text=f"⏱️ {secs}s",
                callback_data=f"auction:timer:{set_number}:{category}:{secs}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="⏰ Custom",
            callback_data=f"auction:timer:custom:{set_number}:{category}",
        )
    ])
    rows.append([
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data="auction:cancel_start",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
