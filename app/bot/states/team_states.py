from aiogram.fsm.state import State, StatesGroup


class TeamCreationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_short_code = State()
    confirming = State()

class TeamLogoStates(StatesGroup):
    waiting_for_photo = State()