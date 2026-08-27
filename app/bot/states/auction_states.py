from aiogram.fsm.state import State, StatesGroup


class AuctionStates(StatesGroup):
    waiting_for_set_number = State()
    waiting_for_player_category = State()
    waiting_for_bid_timer = State()
