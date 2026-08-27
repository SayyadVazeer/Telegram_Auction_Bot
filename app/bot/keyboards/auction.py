from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def auction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔨 BID +0.50",
                    callback_data="auction_bid:0.50",
                ),
                InlineKeyboardButton(
                    text="🔨 BID +1.00",
                    callback_data="auction_bid:1.00",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔨 CUSTOM BID",
                    callback_data="auction_custom_bid",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="SOLD",
                    callback_data="auction_sold",
                ),
                InlineKeyboardButton(
                    text="UNSOLD",
                    callback_data="auction_unsold",
                ),
            ],
        ]
    )
