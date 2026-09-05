from decimal import Decimal

from app.bot.keyboards.auction import auction_keyboard
from app.bot.keyboards.home import alphabet_keyboard, home_keyboard


def test_home_keyboard_contains_expected_public_actions() -> None:
    callbacks = {button.callback_data for row in home_keyboard(is_admin=False, is_owner=False).inline_keyboard for button in row}
    assert {"home:players", "home:teams", "home:tournament", "home:help"} <= callbacks


def test_auction_keyboard_admin_controls() -> None:
    callbacks = {button.callback_data for row in auction_keyboard(Decimal("0.25"), is_admin=True).inline_keyboard for button in row}
    assert "auction:pause" in callbacks
    assert "auction:stop" in callbacks
    # Only admin controls — no bid buttons
    assert not any(cb.startswith("auction:bid_increment") for cb in callbacks)


def test_alphabet_keyboard_has_all_letters() -> None:
    callbacks = {button.callback_data for row in alphabet_keyboard().inline_keyboard for button in row}
    assert "players:letter:all:A" in callbacks
    assert "players:letter:all:Z" in callbacks
