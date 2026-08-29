from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy import func, select

from app.bot.filters.admin import get_admin_ids
from app.bot.states.auction_states import AdminPlayerStates
from app.bot.keyboards.home import (
    admin_panel_keyboard,
    alphabet_keyboard,
    home_keyboard,
    player_list_keyboard,
)
from app.bot.keyboards.team import team_list_keyboard
from app.database.models.auction import AuctionResult, AuctionRun
from app.database.models.player import Player
from app.database.session import AsyncSessionLocal
from app.repositories.team_repository import get_team_by_owner, get_teams_by_tournament
from app.services.tournament_service import TournamentService
from app.utils.enums import AuctionResultStatus

router = Router()


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in get_admin_ids()


async def show_home(message: Message, user_id: int | None) -> None:
    is_owner = False
    if message.chat.type in {"group", "supergroup"} and user_id:
        async with AsyncSessionLocal() as session:
            tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
            is_owner = bool(tournament and await get_team_by_owner(session, tournament.id, user_id))
    await message.answer(
        "Telegram Auction Bot\n\nChoose an option below.",
        reply_markup=home_keyboard(is_admin=is_admin(user_id), is_owner=is_owner),
    )


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await show_home(message, message.from_user.id if message.from_user else None)


@router.callback_query(F.data == "home:back")
async def home_back(callback: CallbackQuery) -> None:
    if callback.message:
        await show_home(callback.message, callback.from_user.id)
    await callback.answer()


# ── players ───────────────────────────────────────────────────────

@router.callback_query(F.data == "home:players")
async def players_home(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(
            "Players\n\nChoose the first letter of a player's name.",
            reply_markup=alphabet_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("players:letter:"))
async def players_by_letter(callback: CallbackQuery) -> None:
    letter = callback.data.rsplit(":", 1)[-1]
    await _show_player_page(callback, letter, 0)


@router.callback_query(F.data.startswith("players:page:"))
async def players_page(callback: CallbackQuery) -> None:
    _, _, letter, page_text = callback.data.split(":")
    await _show_player_page(callback, letter, int(page_text))


async def _show_player_page(callback: CallbackQuery, letter: str, page: int) -> None:
    if not callback.message:
        return
    page_size = 10
    async with AsyncSessionLocal() as session:
        filter_by_letter = Player.name.ilike(f"{letter}%")
        total_players = await session.scalar(
            select(func.count()).select_from(Player).where(filter_by_letter)
        ) or 0
        players = list(
            (
                await session.execute(
                    select(Player)
                    .where(filter_by_letter)
                    .order_by(Player.name)
                    .offset(page * page_size)
                    .limit(page_size)
                )
            ).scalars()
        )
    text = (
        f"No players found starting with {letter}."
        if not players
        else f"Players -- {letter} (Page {page + 1})\n\n"
        + "\n".join(
            f"* {p.name} {'(Overseas)' if p.is_overseas else ''}\n  {p.role} | {p.country} | Set {p.set_number} | Rs.{Decimal(str(p.base_price_cr)):.2f} Cr"
            for p in players
        )
    )
    await callback.message.edit_text(
        text,
        reply_markup=player_list_keyboard(letter, page, total_players, page_size=page_size),
    )
    await callback.answer()


@router.callback_query(F.data == "players:main")
async def players_main_menu(callback: CallbackQuery) -> None:
    if callback.message:
        await show_home(callback.message, callback.from_user.id)
    await callback.answer()


# ── teams ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "home:teams")
async def teams_home(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        teams = await get_teams_by_tournament(session, tournament.id) if tournament else []
    if not tournament:
        await callback.answer("❌ No tournament configured.", show_alert=True)
        return
    await callback.message.answer(
        f"🏏 Teams -- {tournament.name}",
        reply_markup=team_list_keyboard(teams),
    )
    await callback.answer()


# ── tournament ────────────────────────────────────────────────────

@router.callback_query(F.data == "home:tournament")
async def tournament_home(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        run = (
            (
                await session.execute(
                    select(AuctionRun)
                    .where(AuctionRun.tournament_id == tournament.id)
                    .order_by(AuctionRun.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if tournament
            else None
        )
    if not tournament:
        await callback.answer("❌ No tournament configured.", show_alert=True)
        return
    await callback.message.answer(
        f"{tournament.name}\n\n"
        f"Team purse: Rs.{tournament.purse_cr:.2f} Cr\n"
        f"Players/team: {tournament.max_players_per_team}\n"
        f"Overseas limit: {tournament.max_overseas_players}\n"
        f"Minimum increment: Rs.{tournament.minimum_bid_increment_cr:.2f} Cr\n"
        f"Auction: {run.status.title() if run else 'Not started'}"
    )
    await callback.answer()


# ── my team ───────────────────────────────────────────────────────

@router.callback_query(F.data == "home:my_team")
async def my_team_home(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        team = await get_team_by_owner(session, tournament.id, callback.from_user.id) if tournament else None
    if not team:
        await callback.answer("❌ You do not own a team.", show_alert=True)
        return

    # Get full team info
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(callback.message.chat.id)
        results = list(
            (
                await session.execute(
                    select(AuctionResult, Player)
                    .join(Player, Player.id == AuctionResult.player_id)
                    .where(
                        AuctionResult.winning_team_id == team.id,
                        AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                    )
                    .order_by(AuctionResult.final_bid_cr.desc())
                )
            ).all()
        )

    spent = sum((Decimal(str(result.final_bid_cr)) for result, _ in results), Decimal("0"))
    overseas = sum(1 for _, player in results if player.is_overseas)
    roster = (
        "\n".join(
            f"* {player.name} {'(Overseas)' if player.is_overseas else ''} -- Rs.{result.final_bid_cr:.2f} Cr"
            for result, player in results
        )
        or "No players purchased yet."
    )

    text = (
        f"{team.name} ({team.short_code})\n"
        f"Owner: @{team.owner_username}\n\n"
    )
    if tournament:
        text += (
            f"Remaining purse: Rs.{Decimal(str(tournament.purse_cr)) - spent:.2f} Cr\n"
            f"Players: {len(results)}/{tournament.max_players_per_team}\n"
            f"Overseas: {overseas}/{tournament.max_overseas_players}\n\n"
        )
    text += "Purchased players:\n" + roster

    if team.logo_file_id:
        try:
            await callback.message.answer_photo(photo=team.logo_file_id, caption=text)
        except Exception:
            await callback.message.answer(text)
    else:
        await callback.message.answer(text)
    await callback.answer()


# ── admin panel ───────────────────────────────────────────────────

@router.callback_query(F.data == "home:admin")
async def admin_home(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer(
        "🛠️ Admin Panel",
        reply_markup=admin_panel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:players")
async def admin_players_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_players_keyboard
    await callback.message.answer("👥 Player Management", reply_markup=admin_players_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:tournaments")
async def admin_tournaments_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("🏆 Use /create_tournament")
    await callback.answer()


@router.callback_query(F.data == "admin:teams")
async def admin_teams_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("Use /add_team to add a new team.\nUse /assign_owner to assign an owner.")
    await callback.answer()


@router.callback_query(F.data == "admin:auction")
async def admin_auction_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer(
        "Auction commands:\n\n"
        "/start_auction - Start auction\n"
        "/pause_auction - Pause\n"
        "/resume_auction - Resume\n"
        "/stop_auction - Stop\n"
        "/status - View status"
    )
    await callback.answer()



# ── help ──────────────────────────────────────────────────────────


# -- admin player view --

@router.callback_query(F.data == "admin:players:view")
async def admin_players_view(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await _show_admin_player_page(callback, 0)

async def _show_admin_player_page(callback: CallbackQuery, page: int) -> None:
    if not callback.message:
        return
    page_size = 10
    async with AsyncSessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(Player)) or 0
        players = list((await session.execute(
            select(Player).order_by(Player.player_id).offset(page * page_size).limit(page_size)
        )).scalars())
    if not players:
        await callback.message.edit_text("No players found.")
        await callback.answer()
        return
    text = f"Players (Page {page + 1}/{(total + page_size - 1) // page_size})\n\n"
    text += "\n".join(f"{p.player_id} | {p.name}" for p in players)
    from app.bot.keyboards.home import admin_player_list_keyboard
    await callback.message.edit_text(text, reply_markup=admin_player_list_keyboard(page, total, page_size))
    await callback.answer()

@router.callback_query(F.data.startswith("admin:players:page:"))
async def admin_players_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[-1])
    await _show_admin_player_page(callback, page)

# -- admin player add --

@router.callback_query(F.data == "admin:players:add")
async def admin_players_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    # Auto-generate next player ID
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player.player_id).order_by(Player.id.desc()).limit(1))
        last_id = result.scalar()
        if last_id and last_id.startswith("PLY"):
            num = int(last_id[3:]) + 1
        else:
            num = 1
        new_id = f"PLY{num:04d}"
    await state.clear()
    await state.update_data(player_id=new_id)
    await state.set_state(AdminPlayerStates.waiting_for_name)
    msg = "New player ID: " + new_id + chr(10) + chr(10) + "Enter the player name:" + chr(10) + "Use /cancel to cancel."
    await callback.message.answer(msg)
    await callback.answer()

@router.message(AdminPlayerStates.waiting_for_player_id)
async def add_player_id(message: Message, state: FSMContext) -> None:
    pid = (message.text or "").strip()
    async with AsyncSessionLocal() as session:
        exists = await session.scalar(select(Player).where(Player.player_id == pid))
    if exists:
        await message.answer(f"Player {pid} already exists. Enter a different ID:")
        return
    await state.update_data(player_id=pid)
    await state.set_state(AdminPlayerStates.waiting_for_name)
    await message.answer("Enter the player name:")

@router.message(AdminPlayerStates.waiting_for_name)
async def add_player_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "").strip())
    await state.set_state(AdminPlayerStates.waiting_for_country)
    await message.answer("Enter the country:")

@router.message(AdminPlayerStates.waiting_for_country)
async def add_player_country(message: Message, state: FSMContext) -> None:
    await state.update_data(country=(message.text or "").strip())
    await state.set_state(AdminPlayerStates.waiting_for_role)
    await message.answer("Enter the role (e.g., Batsman, Bowler, All-rounder, Wicketkeeper):")

@router.message(AdminPlayerStates.waiting_for_role)
async def add_player_role(message: Message, state: FSMContext) -> None:
    await state.update_data(role=(message.text or "").strip())
    await state.set_state(AdminPlayerStates.waiting_for_is_overseas)
    await message.answer("Is this player overseas? (yes/no):")

@router.message(AdminPlayerStates.waiting_for_is_overseas)
async def add_player_overseas(message: Message, state: FSMContext) -> None:
    val = (message.text or "").strip().lower()
    if val not in ("yes", "no", "y", "n"):
        await message.answer("Enter yes or no:")
        return
    await state.update_data(is_overseas=val in ("yes", "y"))
    await state.set_state(AdminPlayerStates.waiting_for_set_number)
    await message.answer("Enter the set number:")

@router.message(AdminPlayerStates.waiting_for_set_number)
async def add_player_set(message: Message, state: FSMContext) -> None:
    try:
        sn = int((message.text or "").strip())
        if sn <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Enter a valid positive number:")
        return
    await state.update_data(set_number=sn)
    await state.set_state(AdminPlayerStates.waiting_for_base_price)
    await message.answer("Enter the base price in Cr (e.g., 2.00):")

@router.message(AdminPlayerStates.waiting_for_base_price)
async def add_player_price(message: Message, state: FSMContext) -> None:
    from decimal import Decimal, InvalidOperation
    try:
        bp = Decimal((message.text or "").strip())
        if bp <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer("Enter a valid positive number:")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        player = Player(
            player_id=data["player_id"],
            name=data["name"],
            country=data["country"],
            role=data["role"],
            is_overseas=data["is_overseas"],
            set_number=data["set_number"],
            base_price_cr=bp,
            telegram_photo_path=f"data/photos/{data['player_id']}.jpg",
        )
        session.add(player)
        await session.commit()
    await state.clear()
    await message.answer(
        f"Player added!\n\nID: {data['player_id']}\n"
        f"Name: {data['name']}\nCountry: {data['country']}\n"
        f"Role: {data['role']}\nOverseas: {data['is_overseas']}\n"
        f"Set: {data['set_number']}\nBase Price: Rs.{bp:.2f} Cr"
    )

# -- admin player edit --

@router.callback_query(F.data == "admin:players:edit")
async def admin_players_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminPlayerStates.editing_player_id)
    await callback.message.answer("Enter the player ID to edit (e.g., PLY0001):")
    await callback.answer()

@router.message(AdminPlayerStates.editing_player_id)
async def edit_player_id(message: Message, state: FSMContext) -> None:
    pid = (message.text or "").strip()
    async with AsyncSessionLocal() as session:
        player = await session.scalar(select(Player).where(Player.player_id == pid))
    if not player:
        await message.answer(f"Player {pid} not found. Try again:")
        return
    await state.update_data(player_id=pid)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    fields = ["name", "country", "role", "is_overseas", "set_number", "base_price_cr"]
    rows = [[InlineKeyboardButton(text=f, callback_data=f"admin:edit_field:{f}")] for f in fields]
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="admin:players")])
    await message.answer(f"Editing {player.name} ({pid})\nSelect field to edit:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await state.set_state(AdminPlayerStates.editing_field)

@router.callback_query(F.data.startswith("admin:edit_field:"), AdminPlayerStates.editing_field)
async def edit_field_selected(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":")[-1]
    await state.update_data(edit_field=field)
    await state.set_state(AdminPlayerStates.editing_value)
    await callback.message.answer(f"Enter the new value for {field}:")
    await callback.answer()

@router.message(AdminPlayerStates.editing_value)
async def edit_field_value(message: Message, state: FSMContext) -> None:
    from decimal import Decimal
    data = await state.get_data()
    field = data["edit_field"]
    value = (message.text or "").strip()

    if field == "set_number":
        try:
            value = int(value)
        except ValueError:
            await message.answer("Enter a valid number:")
            return
    elif field == "base_price_cr":
        try:
            value = Decimal(value)
        except Exception:
            await message.answer("Enter a valid decimal:")
            return
    elif field == "is_overseas":
        value = value.lower() in ("yes", "y", "true", "1")

    async with AsyncSessionLocal() as session:
        player = await session.scalar(select(Player).where(Player.player_id == data["player_id"]))
        if player:
            setattr(player, field, value)
            await session.commit()
            await message.answer(f"Updated {field} to {value} for {player.name}.")
        else:
            await message.answer("Player not found.")
    await state.clear()

# -- admin player delete --

@router.callback_query(F.data == "admin:players:delete")
async def admin_players_delete_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminPlayerStates.deleting_player_id)
    await callback.message.answer("Enter the player ID to delete (e.g., PLY0001):")
    await callback.answer()

@router.message(AdminPlayerStates.deleting_player_id)
async def delete_player_id(message: Message, state: FSMContext) -> None:
    pid = (message.text or "").strip()
    async with AsyncSessionLocal() as session:
        player = await session.scalar(select(Player).where(Player.player_id == pid))
    if not player:
        await message.answer(f"Player {pid} not found. Try again:")
        return
    await state.update_data(delete_player_id=pid, delete_player_name=player.name)
    await state.set_state(AdminPlayerStates.delete_confirm)
    await message.answer(f"Delete {player.name} ({pid})? This cannot be undone.\nType yes to confirm:")

@router.message(AdminPlayerStates.delete_confirm)
async def delete_player_confirm(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip().lower() != "yes":
        await state.clear()
        await message.answer("Deletion cancelled.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        player = await session.scalar(select(Player).where(Player.player_id == data["delete_player_id"]))
        if player:
            await session.delete(player)
            await session.commit()
            await message.answer(f"Deleted {player.name} ({player.player_id}).")
        else:
            await message.answer("Player not found.")
    await state.clear()

# -- admin manage buttons --

@router.callback_query(F.data == "admin:manage:add")
async def admin_manage_add_button(callback: CallbackQuery) -> None:
    await callback.message.answer("Reply to the user message with /add_admin\nor use /add_admin <user_id>")
    await callback.answer()

@router.callback_query(F.data == "admin:manage:remove")
async def admin_manage_remove_button(callback: CallbackQuery) -> None:
    await callback.message.answer("👇 /remove_admin <user_id>")
    await callback.answer()

@router.callback_query(F.data == "admin:manage:list")
async def admin_manage_list_button(callback: CallbackQuery) -> None:
    from app.services.admin_service import get_admin_ids as get_all_admin_ids
    admins = get_all_admin_ids()
    lines = ["  - " + str(aid) for aid in sorted(admins)]
    admin_list = chr(10).join(lines)
    await callback.message.answer("👮 Current admins:" + chr(10) + admin_list)
    await callback.answer()


async def send_help(message: Message, user: User) -> None:
    guide = "Bot commands\n\n"
    guide += "Everyone:\n"
    guide += "  /start - Main menu\n"
    guide += "  /help - This message\n"
    guide += "  /teams - View all teams\n"

    if is_admin(user.id):
        guide += "\nAdmin:\n"
        guide += "  /create_tournament - Create tournament\n"
        guide += "  /add_team - Add a team\n"
        guide += "  /assign_owner - Assign team owner\n"
        guide += "  /start_auction - Start auction\n"
        guide += "  /pause_auction - Pause auction\n"
        guide += "  /resume_auction - Resume auction\n"
        guide += "  /stop_auction - Stop auction\n"
        guide += "  /status - Auction status\n"
        guide += "  /player_image_change_generator - Upload player photos\n"
        guide += "  /complete_tournament - Delete tournament\n"

    # Check if user is a team owner
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        if tournament:
            team = await get_team_by_owner(session, tournament.id, user.id)
            if team:
                guide += f"\nTeam owner ({team.short_code}):\n"
                guide += "  /bid <amount> - Place bid\n"
                guide += "  /b <amount> - Place bid (short)\n"
                guide += "  /team_logo - Upload team logo\n"
                guide += "  /my_team - View your team\n"
                guide += "  /swap_player - Swap player with another team\n"

    try:
        await message.bot.send_message(user.id, guide)
    except Exception:
        await message.answer(
            "I cannot send you a private message yet. "
            "Open the bot in a private chat, press Start, then use /help again."
        )
    else:
        if message.chat.type != "private":
            await message.answer("📨 Sent command guide in private message.")


@router.callback_query(F.data == "home:help")
async def help_button(callback: CallbackQuery) -> None:
    if callback.message:
        await send_help(callback.message, callback.from_user)
    await callback.answer()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    if message.from_user:
        await send_help(message, message.from_user)


@router.callback_query(F.data == "admin:manage_admins")
async def admin_manage_admins(callback: CallbackQuery) -> None:
    from app.config.settings import settings
    from app.services.admin_service import get_admin_ids
    static_ids = set()
    if settings.admin_ids.strip():
        static_ids = {int(x.strip()) for x in settings.admin_ids.split(",") if x.strip()}
    if callback.from_user.id not in static_ids:
        await callback.answer("🛡️ Only .env admins can manage.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_manage_keyboard
    await callback.message.answer("👮 Admin Management", reply_markup=admin_manage_keyboard())
    await callback.answer()
