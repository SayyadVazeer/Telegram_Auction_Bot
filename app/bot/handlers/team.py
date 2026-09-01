import re
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sqlalchemy import select



from app.bot.keyboards.team import (
    team_confirmation_keyboard,
    team_edit_keyboard,
    team_list_keyboard
)
from app.bot.states.team_states import (
    TeamCreationStates,
    TeamLogoStates,
)

from app.repositories.team_repository import (
    get_team_by_owner_or_coowner,
    get_teams_by_tournament,
)
from app.repositories.tournament_repository import (
    get_tournament_by_chat_id,
)

from app.database.session import AsyncSessionLocal
from app.repositories.team_repository import (
    create_team,
    get_team_by_name,
    get_team_by_short_code,
    assign_team_owner,
    get_team_by_id,
    get_team_by_owner,
)
from app.repositories.tournament_repository import (
    get_tournament_by_chat_id,
)

from app.database.models.team import Team
from app.database.models.auction import AuctionResult
from app.database.models.player import Player
from app.utils.enums import AuctionResultStatus

router = Router()


def valid_short_code(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{2,4}", value))


async def show_team_confirmation(
    message: Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()

    await state.set_state(
        TeamCreationStates.confirming
    )

    text = (
        "🏏 New Team\n\n"
        f"Team Name: {data['name']}\n"
        f"Short Code: {data['short_code']}\n\n"
        "Owner: Not assigned\n"
        "Logo: Not uploaded\n\n"
        "Please confirm:"
    )

    await message.answer(
        text,
        reply_markup=team_confirmation_keyboard(),
    )


@router.message(Command("add_team"))
async def add_team_start(
    message: Message,
    state: FSMContext,
) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(
            "⚠️ This command can only be used "
            "inside the tournament group."
        )
        return

    await state.clear()

    await state.set_state(
        TeamCreationStates.waiting_for_name
    )

    await message.answer(
        "🏏 Add Team\n\n"
        "Enter the team name.\n\n"
        "Use /cancel to cancel."
    )


@router.message(TeamCreationStates.waiting_for_name)
async def team_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = (message.text or "").strip()

    if not name:
        await message.answer(
            "❌ Team name cannot be empty."
        )
        return

    if len(name) > 150:
        await message.answer(
            "❌ Team name must be 150 characters or fewer."
        )
        return

    await state.update_data(name=name)

    data = await state.get_data()

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_team_confirmation(message, state)
        return

    await state.set_state(
        TeamCreationStates.waiting_for_short_code
    )

    await message.answer(
        "🔤 Enter the team short code.\n\n"
        "It must contain 2 to 4 letters only.\n"
        "Example: CSK"
    )


@router.message(TeamCreationStates.waiting_for_short_code)
async def team_short_code(
    message: Message,
    state: FSMContext,
) -> None:
    short_code = (message.text or "").strip()

    if not valid_short_code(short_code):
        await message.answer(
            "❌ Short code must contain 2 to 4 letters only."
        )
        return

    short_code = short_code.upper()

    await state.update_data(
        short_code=short_code
    )

    data = await state.get_data()

    if data.get("editing"):
        await state.update_data(editing=False)
        await show_team_confirmation(message, state)
        return

    await show_team_confirmation(message, state)


@router.callback_query(
    TeamCreationStates.confirming,
    F.data == "team:edit",
)
async def team_edit(
    callback: CallbackQuery,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=team_edit_keyboard()
    )

    await callback.answer()


@router.callback_query(
    TeamCreationStates.confirming,
    F.data == "team:cancel",
)
async def team_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    await callback.message.edit_text(
        "❌ Team creation cancelled."
    )

    await callback.answer()


@router.callback_query(
    TeamCreationStates.confirming,
    F.data == "team:edit:back",
)
async def team_edit_back(
    callback: CallbackQuery,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=team_confirmation_keyboard()
    )

    await callback.answer()


@router.callback_query(
    TeamCreationStates.confirming,
    F.data == "team:edit:name",
)
async def team_edit_name(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.update_data(editing=True)

    await state.set_state(
        TeamCreationStates.waiting_for_name
    )

    await callback.message.answer(
        "✏️ Enter the new team name:"
    )

    await callback.answer()


@router.callback_query(
    TeamCreationStates.confirming,
    F.data == "team:edit:short_code",
)
async def team_edit_short_code(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.update_data(editing=True)

    await state.set_state(
        TeamCreationStates.waiting_for_short_code
    )

    await callback.message.answer(
        "✏️ Enter the new short code:"
    )

    await callback.answer()

@router.callback_query(
    TeamCreationStates.confirming,
    F.data == "team:create",
)
async def team_create_confirmed(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    chat_id = callback.message.chat.id
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        tournament = await get_tournament_by_chat_id(
            session,
            chat_id,
        )

        if tournament is None:
            await callback.answer(
                "❌ No tournament in this group.",
                show_alert=True,
            )
            return

        existing_name = await get_team_by_name(
            session,
            tournament.id,
            data["name"],
        )

        if existing_name is not None:
            await callback.answer(
                "⚠️ Team name already exists.",
                show_alert=True,
            )
            return

        existing_code = await get_team_by_short_code(
            session,
            tournament.id,
            data["short_code"],
        )

        if existing_code is not None:
            await callback.answer(
                "⚠️ Short code already in use.",
                show_alert=True,
            )
            return

        team = await create_team(
            session,
            tournament_id=tournament.id,
            name=data["name"],
            short_code=data["short_code"],
        )

        await session.commit()

    await state.clear()

    await callback.message.edit_text(
        "✅ Team created successfully!\n\n"
        f"🏏 {team.name}\n"
        f"🔤 Short Code: {team.short_code}\n\n"
        "👤 Owner: Not assigned\n"
        "🖼 Logo: Not uploaded"
    )

    await callback.answer("Team created.")

@router.message(Command("teams"))
async def view_teams(
    message: Message,
) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(
            "⚠️ This command can only be used "
            "inside the tournament group."
        )
        return

    async with AsyncSessionLocal() as session:
        tournament = await get_tournament_by_chat_id(
            session,
            message.chat.id,
        )

        if tournament is None:
            await message.answer(
                "⚠️ No tournament exists in this group."
            )
            return

        teams = await get_teams_by_tournament(
            session,
            tournament.id,
        )

    if not teams:
        await message.answer(
            f"👥 Teams — {tournament.name}\n\n"
            "No teams have been registered yet."
        )
        return

    text = (
        f"👥 Teams — {tournament.name}\n\n"
        f"Registered teams: {len(teams)}"
    )

    await message.answer(
        text,
        reply_markup=team_list_keyboard(teams),
    )

async def send_team_info(
    message: Message,
    team: Team,
) -> None:
    owner_display = "Not assigned"

    if team.owner_username:
        owner_display = f"@{team.owner_username}"
    elif team.owner_telegram_id:
        owner_display = str(team.owner_telegram_id)

    coowner_display = ""
    if team.co_owner_username:
        coowner_display = f"\n👤 Co-owner: @{team.co_owner_username}"
    elif team.co_owner_telegram_id:
        coowner_display = "\n👤 Co-owner: (username not available)"

    text = (
        f"🏏 {team.name}\n"
        f"🔠 {team.short_code}\n\n"
        f"👤 Owner: {owner_display}{coowner_display}"
    )

    if team.logo_file_id:
        await message.answer_photo(
            photo=team.logo_file_id,
            caption=text,
            reply_markup=team_edit_keyboard(team),
        )
    else:
        await message.answer(
            text + "\n🖼️ Logo: Not uploaded",
            reply_markup=team_edit_keyboard(team),
        )


@router.callback_query(
    F.data.startswith("team:view:")
)
async def view_team(
    callback: CallbackQuery,
) -> None:
    team_id = int(callback.data.split(":")[-1])

    async with AsyncSessionLocal() as session:
        team = await session.get(Team, team_id)
        if team is not None:
            tournament = await get_tournament_by_chat_id(session, callback.message.chat.id)
            results = list((await session.execute(
                select(AuctionResult, Player)
                .join(Player, Player.id == AuctionResult.player_id)
                .where(
                    AuctionResult.winning_team_id == team.id,
                    AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                )
                .order_by(AuctionResult.final_bid_cr.desc())
            )).all())

    if team is None:
        await callback.answer(
            "❌ Team not found.",
            show_alert=True,
        )
        return

    owner = (
        f"@{team.owner_username}"
        if team.owner_username
        else "Not assigned"
    )

    coowner = (
        f"@{team.co_owner_username}"
        if team.co_owner_username
        else ("Username not set" if team.co_owner_telegram_id else "None")
    )

    text = (
        f"🏏 {team.name}\n\n"
        f"🔠 Short Code: {team.short_code}\n"
        f"👤 Owner: {owner}\n"
        f"👤 Co-owner: {coowner}\n"
    )


    spent = sum((Decimal(str(result.final_bid_cr)) for result, _ in results), Decimal("0"))
    overseas = sum(1 for _, player in results if player.is_overseas)
    roster = "\n".join(
        f"• {player.name} {'✈️' if player.is_overseas else ''} — ₹{result.final_bid_cr:.2f} Cr"
        for result, player in results
    ) or "No players purchased yet."
    if tournament:
        text += (
            f"💰 Remaining purse: ₹{Decimal(str(tournament.purse_cr)) - spent:.2f} Cr\n"
            f"👥 Players: {len(results)}/{tournament.max_players_per_team}\n"
            f"✈️ Overseas: {overseas}/{tournament.max_overseas_players}\n\n"
        )
    text += "Purchased players (highest price first):\n" + roster

    if team.logo_file_id:
        await callback.message.answer_photo(
            photo=team.logo_file_id,
            caption=text,
        )
    else:
        await callback.message.answer(
            text + "\n"
            f"🖼 Logo: Not uploaded"
        )

    await callback.answer()


@router.message(Command("assign_owner"))
async def assign_owner(
    message: Message,
) -> None:
    # Must be a reply to the owner's message
    if message.reply_to_message is None:
        await message.answer(
            "⚠️ You must reply to the owner's message "
            "when using this command.\n\n"
            "Example:\n"
            "/assign_owner CSK"
        )
        return

    parts = (message.text or "").split()

    if len(parts) != 2:
        await message.answer(
            "⚠️ Usage:\n"
            "/assign_owner CSK"
        )
        return

    short_code = parts[1].strip().upper()

    if not valid_short_code(short_code):
        await message.answer(
            "❌ Team short code must contain "
            "2 to 4 letters only."
        )
        return

    owner_user = message.reply_to_message.from_user

    if owner_user is None:
        await message.answer(
            "❌ Could not identify the owner "
            "from the replied message."
        )
        return

    async with AsyncSessionLocal() as session:
        tournament = await get_tournament_by_chat_id(
            session,
            message.chat.id,
        )

        if tournament is None:
            await message.answer(
                "⚠️ No tournament exists in this group."
            )
            return

        result = await session.execute(
            select(Team).where(
                Team.tournament_id == tournament.id,
                Team.short_code == short_code,
            )
        )

        team = result.scalar_one_or_none()

        if team is None:
            await message.answer(
                f"❌ No team with short code "
                f"{short_code} exists in this tournament."
            )
            return

        existing_team = await get_team_by_owner(
            session,
            tournament.id,
            owner_user.id,
        )

        if existing_team is not None:
            await message.answer(
                "⚠️ This Telegram user is already "
                "the owner of another team.\n\n"
                f"Team: {existing_team.name} "
                f"({existing_team.short_code})"
            )
            return

        # Check if user is already a co-owner of another team
        coowner_result = await session.execute(
            select(Team).where(
                Team.co_owner_telegram_id == owner_user.id,
                Team.tournament_id == tournament.id,
            )
        )
        coowner_team = coowner_result.scalar_one_or_none()
        if coowner_team is not None:
            await message.answer(
                "⚠️ This Telegram user is already "
                "a co-owner of another team.\n\n"
                f"Team: {coowner_team.name} "
                f"({coowner_team.short_code})"
            )
            return

        if team.owner_telegram_id is not None:
            current_owner = (
                f"@{team.owner_username}"
                if team.owner_username
                else str(team.owner_telegram_id)
            )

            await message.answer(
                "⚠️ This team already has an owner.\n\n"
                f"Team: {team.name} ({team.short_code})\n"
                f"Owner: {current_owner}"
            )
            return

        username = owner_user.username

        await assign_team_owner(
            session,
            team,
            owner_user.id,
            username,
        )

        await session.commit()

    owner_display = (
        f"@{username}"
        if username
        else owner_user.full_name
    )

    await message.answer(
        "✅ Team owner assigned!\n\n"
        f"🏏 Team: {team.name}\n"
        f"🔤 Code: {team.short_code}\n"

        f"👤 Owner: {owner_display}"
    )

@router.message(Command("team_logo"))
async def team_logo_start(
    message: Message,
    state: FSMContext,
) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer(
            "⚠️ This command can only be used "
            "inside the tournament group."
        )
        return

    async with AsyncSessionLocal() as session:
        tournament = await get_tournament_by_chat_id(
            session,
            message.chat.id,
        )

        if tournament is None:
            await message.answer(
                "⚠️ No tournament exists in this group."
            )
            return

        team = await get_team_by_owner_or_coowner(
            session, tournament.id, message.from_user.id,
        )

    if team is None:
        await message.answer(
            "❌ You are not assigned as the owner "
            "of a team in this tournament."
        )
        return

    await state.clear()

    await state.update_data(
        team_id=team.id,
        team_name=team.name,
        team_short_code=team.short_code,
    )

    await state.set_state(
        TeamLogoStates.waiting_for_photo
    )

    await message.answer(
        f"🖼️ Team Logo — {team.short_code}\n\n"
        "Please send the team logo/photo.\n\n"
        "Send /cancel to cancel."
    )

@router.message(TeamLogoStates.waiting_for_photo)
async def team_logo_photo(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.photo:
        await message.answer(
            "❌ Please send an image/photo.\n\n"
            "Send /cancel to cancel."
        )
        return

    data = await state.get_data()

    team_id = data.get("team_id")

    if team_id is None:
        await state.clear()
        await message.answer(
            "❌ Team information was lost. "
            "Please start again with /team_logo."
        )
        return

    photo = message.photo[-1]

    async with AsyncSessionLocal() as session:
        team = await get_team_by_id(
            session,
            team_id,
        )

        if team is None:
            await state.clear()
            await message.answer(
                "❌ Team no longer exists."
            )
            return

        # Security check — make sure this user
        # is still owner or co-owner of the team.
        if (team.owner_telegram_id != message.from_user.id
                and team.co_owner_telegram_id != message.from_user.id):
            await state.clear()
            await message.answer(
                "❌ You are not the owner of this team."
            )
            return

        team.logo_file_id = photo.file_id

        await session.commit()

    await state.clear()

    await message.answer_photo(
        photo=photo.file_id,
        caption=(
            f"✅ Team logo updated!\n\n"
            f"🏏 {team.name}\n"
            f"🔤 {team.short_code}"
        ),
    )
