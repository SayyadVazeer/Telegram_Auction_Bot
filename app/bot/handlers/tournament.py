from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.tournament import (
    tournament_confirmation_keyboard,
    tournament_edit_keyboard,
)
from app.bot.states.tournament_states import TournamentCreationStates

from app.database.session import AsyncSessionLocal
from app.repositories.tournament_repository import (
    create_tournament,
    get_tournament_by_chat_id,
)


router = Router()


def is_positive_decimal(value: str) -> bool:
    try:
        return Decimal(value) > 0
    except InvalidOperation:
        return False


def is_positive_integer(value: str) -> bool:
    try:
        return int(value) > 0
    except ValueError:
        return False


async def show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    text = (
        "🏆 Tournament Preview\n\n"
        f"Name: {data['name']}\n\n"
        f"💰 Team purse: ₹{data['purse_cr']:.2f} Cr\n"
        f"🌍 Max overseas: {data['max_overseas_players']}\n"
        f"👥 Max players/team: {data['max_players_per_team']}\n"
        f"📈 Minimum bid increment: "
        f"₹{data['minimum_bid_increment_cr']:.2f} Cr\n\n"
        "Please confirm:"
    )

    await state.set_state(TournamentCreationStates.confirming)

    await message.answer(
        text,
        reply_markup=tournament_confirmation_keyboard(),
    )


@router.message(Command("create_tournament"))
async def create_tournament_start(
    message: Message,
    state: FSMContext,
) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(
            "⚠️ This command can only be used inside the tournament group."
        )
        return

    await state.clear()
    await state.set_state(TournamentCreationStates.waiting_for_name)

    await message.answer(
        "🏆 Create Tournament\n\n"
        "Enter the tournament name:\n\n"
        "Press /cancel at any time to cancel."
    )


@router.message(TournamentCreationStates.waiting_for_name)
async def tournament_name(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text or not message.text.strip():
        await message.answer("❌ Tournament name cannot be empty.")
        return

    name = message.text.strip()

    if len(name) > 150:
        await message.answer(
            "❌ Tournament name must be 150 characters or fewer."
        )
        return

    await state.update_data(name=name)

    data = await state.get_data()

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_confirmation(message, state)
        return


    await state.set_state(
        TournamentCreationStates.waiting_for_purse
    )

    await message.answer(
        "💰 Enter the purse for each team in Crores.\n\n"
        "Example: 100"
    )


@router.message(TournamentCreationStates.waiting_for_purse)
async def tournament_purse(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    if not is_positive_decimal(value):
        await message.answer(
            "❌ Enter a valid positive number.\n\n"
            "Example: 100 or 100.50"
        )
        return

    purse = Decimal(value)

    await state.update_data(purse_cr=purse)

    data = await state.get_data()

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_confirmation(message, state)
        return



    await state.set_state(
        TournamentCreationStates.waiting_for_max_overseas
    )

    await message.answer(
        "🌍 Enter the maximum number of overseas players per team."
    )


@router.message(TournamentCreationStates.waiting_for_max_overseas)
async def tournament_max_overseas(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    if not is_positive_integer(value):
        await message.answer(
            "❌ Enter a valid positive whole number."
        )
        return

    max_overseas = int(value)

    await state.update_data(
        max_overseas_players=max_overseas
    )

    data = await state.get_data()
    
    if data.get("editing"):
        await state.update_data(editing=False)
        await show_confirmation(message, state)
        return
    
    await state.set_state(
        TournamentCreationStates.waiting_for_max_players
    )

    await message.answer(
        "👥 Enter the maximum number of players per team."
    )


@router.message(TournamentCreationStates.waiting_for_max_players)
async def tournament_max_players(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    if not is_positive_integer(value):
        await message.answer(
            "❌ Enter a valid positive whole number."
        )
        return

    max_players = int(value)

    data = await state.get_data()

    if data["max_overseas_players"] > max_players:
        await message.answer(
            "❌ Maximum overseas players cannot be greater "
            "than maximum players per team.\n\n"
            f"Overseas: {data['max_overseas_players']}\n"
            f"Players/team: {max_players}"
        )
        return

    await state.update_data(
        max_players_per_team=max_players
    )

    data = await state.get_data()
    
    if data.get("editing"):
        await state.update_data(editing=False)
        await show_confirmation(message, state)
        return

    await state.set_state(
        TournamentCreationStates.waiting_for_min_bid_increment
    )

    await message.answer(
        "📈 Enter the minimum bid increment in Crores.\n\n"
        "Example: 0.25"
    )


@router.message(
    TournamentCreationStates.waiting_for_min_bid_increment
)
async def tournament_min_bid_increment(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    if not is_positive_decimal(value):
        await message.answer(
            "❌ Enter a valid positive number.\n\n"
            "Example: 0.25"
        )
        return

    increment = Decimal(value)

    await state.update_data(
        minimum_bid_increment_cr=increment
    )

    data = await state.get_data()
    
    if data.get("editing"):
        await state.update_data(editing=False)
        await show_confirmation(message, state)
        return
    
    await show_confirmation(message, state)


@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit",
)
async def tournament_edit(
    callback: CallbackQuery,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=tournament_edit_keyboard()
    )
    await callback.answer()


@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:cancel",
)
async def tournament_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    await callback.message.edit_text(
        "❌ Tournament creation cancelled."
    )

    await callback.answer()


@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit:back",
)
async def tournament_edit_back(
    callback: CallbackQuery,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=tournament_confirmation_keyboard()
    )
    await callback.answer()


@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:create",
)
async def tournament_create_confirmed(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    chat_id = callback.message.chat.id

    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        existing_tournament = await get_tournament_by_chat_id(
            session,
            chat_id,
        )

        if existing_tournament is not None:
            await callback.answer(
                "A tournament already exists in this group.",
                show_alert=True,
            )
            return

        tournament = await create_tournament(
            session,
            telegram_chat_id=chat_id,
            name=data["name"],
            purse_cr=data["purse_cr"],
            max_overseas_players=data["max_overseas_players"],
            max_players_per_team=data["max_players_per_team"],
            minimum_bid_increment_cr=data[
                "minimum_bid_increment_cr"
            ],
        )

        await session.commit()

    await state.clear()

    await callback.message.edit_text(
        "✅ Tournament created successfully!\n\n"
        f"🏆 {tournament.name}\n\n"
        f"💰 Team purse: ₹{tournament.purse_cr:.2f} Cr\n"
        f"🌍 Max overseas: "
        f"{tournament.max_overseas_players}\n"
        f"👥 Max players/team: "
        f"{tournament.max_players_per_team}\n"
        f"📈 Minimum bid increment: "
        f"₹{tournament.minimum_bid_increment_cr:.2f} Cr"
    )

    await callback.answer("Tournament created.")

@router.message(Command("cancel"))
async def cancel_tournament_creation(
    message: Message,
    state: FSMContext,
) -> None:
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "ℹ️ There is no active operation to cancel."
        )
        return

    await state.clear()

    await message.answer(
        "❌ Operation cancelled."
    )

@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit:name",
)
async def edit_tournament_name(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    
    await state.update_data(editing=True)

    await state.set_state(
        TournamentCreationStates.waiting_for_name
    )

    await callback.message.answer(
        "✏️ Enter the new tournament name:"
    )

    await callback.answer()

@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit:purse",
)
async def edit_tournament_purse(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.update_data(editing=True)

    await state.set_state(
        TournamentCreationStates.waiting_for_purse
    )

    await callback.message.answer(
        "✏️ Enter the new team purse in Crores:"
    )

    await callback.answer()

@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit:overseas",
)
async def edit_tournament_overseas(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.update_data(editing=True)

    await state.set_state(
        TournamentCreationStates.waiting_for_max_overseas
    )

    await callback.message.answer(
        "✏️ Enter the new maximum overseas players:"
    )

    await callback.answer()

@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit:max_players",
)
async def edit_tournament_max_players(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.update_data(editing=True)

    await state.set_state(
        TournamentCreationStates.waiting_for_max_players
    )

    await callback.message.answer(
        "✏️ Enter the new maximum players per team:"
    )

    await callback.answer()

@router.callback_query(
    TournamentCreationStates.confirming,
    F.data == "tournament:edit:increment",
)
async def edit_tournament_increment(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.update_data(editing=True)

    await state.set_state(
        TournamentCreationStates.waiting_for_min_bid_increment
    )

    await callback.message.answer(
        "✏️ Enter the new minimum bid increment in Crores:"
    )

    await callback.answer()
