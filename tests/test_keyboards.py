from decimal import Decimal

from app.bot.keyboards.auction import auction_keyboard
from app.bot.keyboards.home import alphabet_keyboard, home_keyboard


def test_home_keyboard_contains_expected_public_actions() -> None:
    callbacks = {button.callback_data for row in home_keyboard(is_admin=False, is_owner=False).inline_keyboard for button in row}
    assert {"home:players", "home:teams", "home:tournament", "home:help"} <= callbacks


def test_auction_keyboard_uses_configured_increment() -> None:
    callbacks = {button.callback_data for row in auction_keyboard(Decimal("0.25")).inline_keyboard for button in row}
    assert "auction:bid_increment:0.25" in callbacks
    assert "auction:bid_increment:0.50" in callbacks


def test_alphabet_keyboard_has_all_letters() -> None:
    callbacks = {button.callback_data for row in alphabet_keyboard().inline_keyboard for button in row}
    assert "players:letter:A" in callbacks
    assert "players:letter:Z" in callbacks
