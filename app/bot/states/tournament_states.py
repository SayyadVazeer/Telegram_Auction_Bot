from aiogram.fsm.state import State, StatesGroup


class TournamentCreationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_purse = State()
    waiting_for_max_overseas = State()
    waiting_for_max_players = State()
    waiting_for_min_bid_increment = State()
    confirming = State()
