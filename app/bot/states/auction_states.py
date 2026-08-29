from aiogram.fsm.state import State, StatesGroup


class AuctionStates(StatesGroup):
    waiting_for_set_number = State()
    waiting_for_player_category = State()
    waiting_for_bid_timer = State()
    waiting_for_custom_bid = State()
    choosing_set_number = State()
    choosing_category = State()


class AdminPlayerStates(StatesGroup):
    waiting_for_player_id = State()
    waiting_for_name = State()
    waiting_for_country = State()
    waiting_for_role = State()
    waiting_for_is_overseas = State()
    waiting_for_set_number = State()
    waiting_for_base_price = State()
    editing_player_id = State()
    editing_field = State()
    editing_value = State()
    deleting_player_id = State()
    delete_confirm = State()
