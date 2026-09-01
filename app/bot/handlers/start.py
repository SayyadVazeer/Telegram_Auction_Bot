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
    filtered_player_list_keyboard,
    home_keyboard,
    player_list_keyboard,
    players_filter_keyboard,
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
        "🏏 Telegram Auction Bot\n\nChoose an option below.",
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
            "👥 Players\n\nChoose an option below.",
            reply_markup=players_filter_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "players:home")
async def players_home_back(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text(
            "👥 Players\n\nChoose an option below.",
            reply_markup=players_filter_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("players:filter:"))
async def players_filter(callback: CallbackQuery) -> None:
    """Handle sold/unsold/not_participated filter - show alphabet for that filter."""
    raw = callback.data.split(":")
    filter_mode = raw[2] if len(raw) >= 3 else "all"
    if filter_mode == "alphabet":
        return
    await callback.message.edit_text(
        f"👥 Players — {filter_mode.replace('_', ' ').title()}\n\nChoose the first letter.",
        reply_markup=alphabet_keyboard(filter_mode=filter_mode),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("players:letter:"))
async def players_by_letter(callback: CallbackQuery) -> None:
    # Format: players:letter:{filter_mode}:{letter}
    parts = callback.data.split(":")
    if len(parts) >= 4:
        filter_mode = parts[2]
        letter = parts[3]
    else:
        filter_mode = "all"
        letter = parts[2]
    await _show_player_page(callback, letter, 0, filter_mode=filter_mode)


@router.callback_query(F.data.startswith("players:page:"))
async def players_page(callback: CallbackQuery) -> None:
    # Format: players:page:{filter_mode}:{letter}:{page}
    parts = callback.data.split(":")
    filter_mode = parts[2]
    letter = parts[3]
    page_text = parts[4]
    await _show_player_page(callback, letter, int(page_text), filter_mode=filter_mode)


async def _show_player_page(callback: CallbackQuery, letter: str, page: int, *, filter_mode: str = "all") -> None:
    if not callback.message:
        return
    page_size = 10
    async with AsyncSessionLocal() as session:
        # Build base query
        query = select(Player)
        count_query = select(func.count()).select_from(Player)
        conditions = []

        if letter and letter != "_":
            conditions.append(Player.name.ilike(f"{letter}%"))

        if filter_mode == "sold":
            sold_sub = select(AuctionResult.player_id).where(
                AuctionResult.result_status == AuctionResultStatus.SOLD.value
            ).distinct().correlate(Player)
            conditions.append(Player.id.in_(sold_sub))
        elif filter_mode == "unsold":
            unsold_sub = select(AuctionResult.player_id).where(
                AuctionResult.result_status == AuctionResultStatus.UNSOLD.value
            ).distinct().correlate(Player)
            conditions.append(Player.id.in_(unsold_sub))
        elif filter_mode == "not_participated":
            # Players with no auction results at all
            any_sub = select(AuctionResult.player_id).where(
                AuctionResult.player_id.isnot(None)
            ).correlate(Player)
            conditions.append(Player.id.not_in(any_sub))

        for cond in conditions:
            query = query.where(cond)
            count_query = count_query.where(cond)

        total_players = await session.scalar(count_query) or 0
        players = list(
            (
                await session.execute(
                    query.order_by(Player.name)
                    .offset(page * page_size)
                    .limit(page_size)
                )
            ).scalars()
        )

    label = filter_mode.replace("_", " ").title() if filter_mode != "all" else "All"
    if not players:
        text = f"No {label.lower()} players found starting with {letter}."
    else:
        text = f"👥 {label} Players — {letter} (Page {page + 1}/{(total_players + page_size - 1) // page_size})\n\n"
        for p in players:
            status = ""
            if filter_mode == "sold":
                status = " ✅ SOLD"
            elif filter_mode == "unsold":
                status = " ❌ UNSOLD"
            overseas = " ✈️" if p.is_overseas else ""
            text += f"\n* {p.name}{overseas}{status}\n  {p.role} | {p.country} | Set {p.set_number} | Rs.{Decimal(str(p.base_price_cr)):.2f} Cr\n  ID: {p.player_id}"

    await callback.message.edit_text(
        text,
        reply_markup=filtered_player_list_keyboard(
            filter_mode, letter, page, total_players,
            page_size=page_size,
        ),
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
    inc = f"Rs.{run.minimum_bid_increment_cr:.2f} Cr" if run and run.minimum_bid_increment_cr else "N/A"
    await callback.message.answer(
        f"🏆 {tournament.name}\n\n"
        f"💰 Team purse: Rs.{tournament.purse_cr:.2f} Cr\n"
        f"👥 Players/team: {tournament.max_players_per_team}\n"
        f"✈️ Overseas limit: {tournament.max_overseas_players}\n"
        f"📊 Minimum increment: {inc}\n"
        f"🔴 Auction: {run.status.title() if run else 'Not started'}"
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
        f"🏏 {team.name} ({team.short_code})\n"
        f"👤 Owner: @{team.owner_username}\n\n"
    )
    if team.co_owner_username:
        text += f"👤 Co-owner: @{team.co_owner_username}\n\n"
    if tournament:
        text += (
            f"💰 Remaining purse: Rs.{Decimal(str(tournament.purse_cr)) - spent:.2f} Cr\n"
            f"👥 Players: {len(results)}/{tournament.max_players_per_team}\n"
            f"✈️ Overseas: {overseas}/{tournament.max_overseas_players}\n\n"
        )
    text += "📋 Purchased players:\n" + roster

    if team.logo_file_id:
        try:
            await callback.message.answer_photo(photo=team.logo_file_id, caption=text)
        except Exception:
            await callback.message.answer(text)
    else:
        await callback.message.answer(text)
    await callback.answer()


async def _show_my_team(message: Message) -> None:
    """Shared logic for /my_team command and callback."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        team = await get_team_by_owner(session, tournament.id, message.from_user.id) if tournament else None
    if not team:
        await message.answer("❌ You do not own a team.")
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
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
    spent = sum((Decimal(str(r.final_bid_cr)) for r, _ in results), Decimal("0"))
    overseas = sum(1 for _, p in results if p.is_overseas)
    roster = (
        "\n".join(
            f"• {p.name} {'✈️' if p.is_overseas else ''} — Rs.{r.final_bid_cr:.2f} Cr"
            for r, p in results
        )
        or "No players purchased yet."
    )
    text = (
        f"🏏 {team.name} ({team.short_code})\n"
        f"👤 Owner: @{team.owner_username}\n\n"
    )
    if team.co_owner_username:
        text += f"👤 Co-owner: @{team.co_owner_username}\n\n"
    if tournament:
        text += (
            f"💰 Remaining purse: Rs.{Decimal(str(tournament.purse_cr)) - spent:.2f} Cr\n"
            f"👥 Players: {len(results)}/{tournament.max_players_per_team}\n"
            f"✈️ Overseas: {overseas}/{tournament.max_overseas_players}\n\n"
        )
    text += "📋 Purchased players:\n" + roster
    if team.logo_file_id:
        try:
            await message.answer_photo(photo=team.logo_file_id, caption=text)
        except Exception:
            await message.answer(text)
    else:
        await message.answer(text)


async def _show_purse(message: Message) -> None:
    """Shared logic for /purse command."""
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("This command can only be used inside the tournament group.")
        return
    async with AsyncSessionLocal() as session:
        tournament = await TournamentService(session).get_by_telegram_chat_id(message.chat.id)
        team = await get_team_by_owner(session, tournament.id, message.from_user.id) if tournament else None
    if not team:
        await message.answer("❌ You do not own a team.")
        return
    async with AsyncSessionLocal() as session:
        spent_result = await session.execute(
            select(func.coalesce(func.sum(AuctionResult.final_bid_cr), 0)).where(
                AuctionResult.tournament_id == team.tournament_id,
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        )
        spent = Decimal(str(spent_result.scalar() or 0))
        # Count players and overseas
        player_count = await session.scalar(
            select(func.count()).select_from(AuctionResult).where(
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
            )
        ) or 0
        overseas_count = await session.scalar(
            select(func.count()).select_from(AuctionResult)
            .join(Player, Player.id == AuctionResult.player_id)
            .where(
                AuctionResult.winning_team_id == team.id,
                AuctionResult.result_status == AuctionResultStatus.SOLD.value,
                Player.is_overseas == True,
            )
        ) or 0
    remaining = Decimal(str(tournament.purse_cr)) - spent
    await message.answer(
        f"💰 {team.name} Purse\n\n"
        f"Total: Rs.{tournament.purse_cr:.2f} Cr\n"
        f"Spent: Rs.{spent:.2f} Cr\n"
        f"Remaining: Rs.{remaining:.2f} Cr\n\n"
        f"👥 Players: {player_count}/{tournament.max_players_per_team}\n"
        f"✈️ Overseas: {overseas_count}/{tournament.max_overseas_players}"
    )


@router.message(Command("my_team"))
async def my_team_command(message: Message) -> None:
    if message.from_user:
        await _show_my_team(message)


@router.message(Command("purse"))
async def purse_command(message: Message) -> None:
    if message.from_user:
        await _show_purse(message)


@router.message(Command("player_photo"))
async def player_photo_command(message: Message) -> None:
    """Send a player's photo by player ID, e.g. /player_photo PLY0015"""
    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "📸 Usage: /player_photo <PLAYER_ID>\n\n"
            "Example: /player_photo PLY0015"
        )
        return

    pid = parts[1].strip().upper()
    async with AsyncSessionLocal() as session:
        player = await session.scalar(
            select(Player).where(Player.player_id == pid)
        )
    if not player:
        await message.answer(
            f"❌ Player \"{pid}\" not found."
        )
        return

    caption = (
        f"📸 {player.name} ({player.player_id})\n"
        f"{player.role} | {player.country}"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.bot.states.auction_states import AdminPlayerStates

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Edit Photo", callback_data=f"player_photo:edit:{pid}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="player_photo:cancel"),
        ],
    ])

    if player.telegram_file_id:
        await message.answer_photo(
            photo=player.telegram_file_id,
            caption=caption,
            reply_markup=kb,
        )
    else:
        await message.answer(
            f"📸 No photo available for {player.name} ({pid}).\n\n"
            "Click Edit Photo to upload one.",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("player_photo:edit:"))
async def player_photo_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    pid = callback.data.split(":")[-1]
    async with AsyncSessionLocal() as session:
        player = await session.scalar(
            select(Player).where(Player.player_id == pid)
        )
    if not player:
        await callback.answer("❌ Player not found.", show_alert=True)
        return
    await state.update_data(player_id=pid, player_name=player.name)
    from app.bot.states.auction_states import AdminPlayerStates
    await state.set_state(AdminPlayerStates.editing_photo)
    await callback.message.answer(
        f"📸 Send a new photo for {player.name} ({pid}).\n\n"
        "Send /cancel to abort."
    )
    await callback.answer()


@router.callback_query(F.data == "player_photo:cancel")
async def player_photo_cancel(callback: CallbackQuery) -> None:
    await callback.answer("Cancelled.")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.message(AdminPlayerStates.editing_photo)
async def player_photo_edit_receive(message: Message, state: FSMContext) -> None:
    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("❌ Cancelled.")
        return
    if not message.photo:
        await message.answer(
            "❌ Please send an image/photo.\n\n"
            "Send /cancel to abort."
        )
        return
    data = await state.get_data()
    pid = data.get("player_id")
    if not pid:
        await state.clear()
        await message.answer("❌ Session expired. Start again with /player_photo.")
        return
    # Get the largest photo size
    photo = message.photo[-1]
    file_id = photo.file_id
    async with AsyncSessionLocal() as session:
        player = await session.scalar(
            select(Player).where(Player.player_id == pid)
        )
        if not player:
            await state.clear()
            await message.answer("❌ Player not found.")
            return
        player.telegram_file_id = file_id
        await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Photo updated for {player.name} ({pid})."
    )


@router.message(Command("add_player"))
async def add_player_command(message: Message, state: FSMContext) -> None:
    """Start the add-player flow via /add_player (same as admin panel button)."""
    if not is_admin(message.from_user.id if message.from_user else None):
        await message.answer("🛡️ Admin access required.")
        return
    # Auto-generate next player ID — fill gaps first
    async with AsyncSessionLocal() as session:
        all_ids = list((await session.execute(select(Player.player_id))).scalars())
        existing = {int(x[3:]) for x in all_ids if x and x.startswith("PLY")}
        if existing:
            max_id = max(existing)
            new_num = None
            for candidate in range(1, max_id + 1):
                if candidate not in existing:
                    new_num = candidate
                    break
            if new_num is None:
                new_num = max_id + 1
        else:
            new_num = 1
        new_id = f"PLY{new_num:04d}"
    await state.clear()
    await state.update_data(player_id=new_id)
    await state.set_state(AdminPlayerStates.waiting_for_name)
    await message.answer(
        f"➕ New player ID: {new_id}\n\n"
        "Enter the player name:\n"
        "Use /cancel to cancel."
    )


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
    from app.bot.keyboards.home import admin_tournament_keyboard
    await callback.message.answer("🏆 Tournament Management", reply_markup=admin_tournament_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:teams")
async def admin_teams_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_teams_keyboard
    await callback.message.answer("🏏 Team Management", reply_markup=admin_teams_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:auction")
async def admin_auction_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_auction_keyboard
    await callback.message.answer("💰 Auction Control", reply_markup=admin_auction_keyboard())
    await callback.answer()



# ── help ──────────────────────────────────────────────────────────


# -- admin player view --

@router.callback_query(F.data == "admin:players:view")
async def admin_players_view(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await _show_admin_player_page(callback, 0)

@router.callback_query(F.data.startswith("admin:players:letter:"))
async def admin_players_letter(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    letter = callback.data.split(":")[-1]
    await _show_admin_player_page(callback, 0, letter=letter)

async def _show_admin_player_page(callback: CallbackQuery, page: int, letter: str | None = None) -> None:
    if not callback.message:
        return
    page_size = 10
    async with AsyncSessionLocal() as session:
        if letter:
            # Filter by player name's first letter (upper)
            upper_letter = letter.upper()
            base_q = select(Player).where(Player.name.ilike(f"{upper_letter}%"))
            count_q = select(func.count()).select_from(Player).where(Player.name.ilike(f"{upper_letter}%"))
        else:
            base_q = select(Player)
            count_q = select(func.count()).select_from(Player)
        total = await session.scalar(count_q) or 0
        players = list((await session.execute(
            base_q.order_by(Player.player_id).offset(page * page_size).limit(page_size)
        )).scalars())
    if not players:
        label = f" starting with '{letter}'" if letter else ""
        await callback.message.edit_text(f"No players found{label}.")
        await callback.answer()
        return
    total_pages = max(1, (total + page_size - 1) // page_size)
    label = f" | Filter: {letter}*" if letter else ""
    text = f"👥 Players (Page {page + 1}/{total_pages}){label}\n\n"
    text += "\n".join(f"{p.player_id} | {p.name}" for p in players)
    from app.bot.keyboards.home import admin_player_list_keyboard
    await callback.message.edit_text(text, reply_markup=admin_player_list_keyboard(page, total, page_size, letter=letter))
    await callback.answer()

@router.callback_query(F.data.startswith("admin:players:page:"))
async def admin_players_page(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    # Format: admin:players:page:{page} or admin:players:page:{letter}:{page}
    if len(parts) == 5:
        # Letter-filtered pagination
        letter = parts[3]
        page = int(parts[4])
        await _show_admin_player_page(callback, page, letter=letter)
    else:
        page = int(parts[-1])
        await _show_admin_player_page(callback, page)

# -- admin player add --

@router.callback_query(F.data == "admin:players:add")
async def admin_players_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    # Auto-generate next player ID — fill gaps first
    async with AsyncSessionLocal() as session:
        all_ids = list((await session.execute(select(Player.player_id))).scalars())
        existing = {int(x[3:]) for x in all_ids if x and x.startswith("PLY")}
        if existing:
            # Find the first gap (missing ID) in the range 1..max
            max_id = max(existing)
            new_num = None
            for candidate in range(1, max_id + 1):
                if candidate not in existing:
                    new_num = candidate
                    break
            if new_num is None:
                # No gaps — append after the last
                new_num = max_id + 1
        else:
            new_num = 1
        new_id = f"PLY{new_num:04d}"
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
    await state.update_data(base_price_cr=str(bp))
    await state.set_state(AdminPlayerStates.waiting_for_photo)
    await message.answer(
        f"✅ Player saved: {data['name']} ({data['player_id']})\n\n"
        "📸 Now send a photo for this player.\n"
        "Send /skip to skip."
    )


@router.message(AdminPlayerStates.waiting_for_photo)
async def add_player_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pid = data.get("player_id")
    if not pid:
        await state.clear()
        await message.answer("❌ Session expired. Start again.")
        return
    if message.text and message.text.strip().lower() in ("/skip", "skip"):
        await state.clear()
        await message.answer(
            f"✅ Player added!\n\n"
            f"ID: {pid}\n"
            f"Name: {data.get('name', '?')}\n"
            f"Country: {data.get('country', '?')}\n"
            f"Role: {data.get('role', '?')}\n"
            f"Base price: Rs.{data.get('base_price_cr', '?')} Cr\n\n"
            "No photo set. Use /player_photo to add one later."
        )
        return
    if not message.photo:
        await message.answer(
            "❌ Please send an image/photo.\n"
            "Send /skip to skip."
        )
        return
    photo = message.photo[-1]
    async with AsyncSessionLocal() as session:
        player = await session.scalar(
            select(Player).where(Player.player_id == pid)
        )
        if player:
            player.telegram_file_id = photo.file_id
            await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Player added!\n\n"
        f"ID: {pid}\n"
        f"Name: {data.get('name', '?')}\n"
        f"Country: {data.get('country', '?')}\n"
        f"Role: {data.get('role', '?')}\n"
        f"Base price: Rs.{data.get('base_price_cr', '?')} Cr\n"
        f"📸 Photo: ✅ Uploaded"
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


# ── Admin sub-panel button handlers ──────────────────────────
# Teams sub-panel

@router.callback_query(F.data == "admin:teams:add")
async def admin_teams_add_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("➕ Send /add_team to add a new team.")
    await callback.answer()


@router.callback_query(F.data == "admin:teams:assign")
async def admin_teams_assign_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("👤 Send /assign_owner <team_code> <user_id> to assign an owner.")
    await callback.answer()


@router.callback_query(F.data == "admin:teams:edit")
async def admin_teams_edit_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("✏️ Send /edit_team to edit a team.")
    await callback.answer()


@router.callback_query(F.data == "admin:teams:delete")
async def admin_teams_delete_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("🗑️ Send /delete_team <team_code> to delete a team.")
    await callback.answer()


@router.callback_query(F.data == "admin:teams:change_owner")
async def admin_teams_change_owner_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("🔄 Send /change_owner <team_code> <new_owner_id> to change owner.")
    await callback.answer()


# Tournaments sub-panel

@router.callback_query(F.data == "admin:tournaments:create")
async def admin_tournaments_create_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("🏆 Send /create_tournament to create a new tournament.")
    await callback.answer()


@router.callback_query(F.data == "admin:tournaments:edit")
async def admin_tournaments_edit_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    from app.database.session import AsyncSessionLocal
    from app.repositories.tournament_repository import get_tournament_by_chat_id
    async with AsyncSessionLocal() as session:
        tournament = await get_tournament_by_chat_id(session, callback.message.chat.id)
    if not tournament:
        await callback.message.answer("❌ No tournament exists in this group. Create one first with /create_tournament")
    else:
        await callback.message.answer(f"✏️ Tournament: {tournament.name}\n\nUse /create_tournament to edit, or /complete_tournament to delete.")
    await callback.answer()


@router.callback_query(F.data == "admin:tournaments:complete")
async def admin_tournaments_complete_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    from app.database.session import AsyncSessionLocal
    from app.repositories.tournament_repository import get_tournament_by_chat_id
    async with AsyncSessionLocal() as session:
        tournament = await get_tournament_by_chat_id(session, callback.message.chat.id)
    if not tournament:
        await callback.message.answer("❌ No tournament exists in this group. Create one first with /create_tournament")
    else:
        await callback.message.answer(f"⚠️ Tournament: {tournament.name}\n\nSend /complete_tournament to delete it.")
    await callback.answer()


# Auction sub-panel

@router.callback_query(F.data == "admin:auction:start")
async def admin_auction_start_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("🔴 Send /start_auction to begin the auction.")
    await callback.answer()


@router.callback_query(F.data == "admin:auction:pause")
async def admin_auction_pause_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("⏸️ Send /pause_auction to pause the auction.")
    await callback.answer()


@router.callback_query(F.data == "admin:auction:resume")
async def admin_auction_resume_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("▶️ Send /resume_auction to resume the auction.")
    await callback.answer()


@router.callback_query(F.data == "admin:auction:stop")
async def admin_auction_stop_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("⏹️ Send /stop_auction to stop the auction.")
    await callback.answer()


@router.callback_query(F.data == "admin:auction:status")
async def admin_auction_status_button(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("🛡️ Admin access required.", show_alert=True)
        return
    await callback.message.answer("ℹ️ Send /status to view auction status.")
    await callback.answer()


async def send_help(message: Message, user: User) -> None:
    guide = "📖 Bot Commands\n\n"
    guide += "👥 Everyone:\n"
    guide += "  /start - Main menu\n"
    guide += "  /help - This message\n"
    guide += "  /help_all - Full admin guide (DM only)\n"
    guide += "  /cancel - Cancel current operation\n"
    guide += "  /teams - View all teams\n"
    guide += "  /my_team - View your team roster\n"
    guide += "  /purse - Check your team purse\n"
    guide += "  /team_logo - Upload team logo\n"
    guide += "  /bid <amount> - Place a bid\n"
    guide += "  /b <amount> - Place bid (short form)\n"
    guide += "  /trade_player - Trade player\n"
    guide += "  /accept_trade - Accept trade proposal\n"
    guide += "  /reject_trade - Reject trade proposal\n"
    guide += "  /add_coowner <team> - Add co-owner to team\n"
    guide += "  /remove_coowner <team> - Remove co-owner\n"
    guide += "  /player_photo <ID> - View/edit player photo\n"
    guide += "\n🛡️ Admin:\n"
    guide += "  /add_player - Add a new player\n"
    guide += "  /create_tournament - Create tournament\n"
    guide += "  /complete_tournament - Complete tournament\n"
    guide += "  /add_team - Add a new team\n"
    guide += "  /assign_owner - Assign owner to a team\n"
    guide += "  /edit_team - Edit team name or code\n"
    guide += "  /delete_team - Delete a team\n"
    guide += "  /change_owner - Change team owner\n"
    guide += "  /start_auction - Start auction for a set\n"
    guide += "  /pause_auction - Pause running auction\n"
    guide += "  /resume_auction - Resume paused auction\n"
    guide += "  /stop_auction - Stop running auction\n"
    guide += "  /next_player - Skip 15s delay\n"
    guide += "  /status - Auction status\n"
    guide += "  /manual_sell - Manually sell player\n"
    guide += "  /manual_unsell - Remove player from team\n"
    guide += "  /trade_on - Enable trading\n"
    guide += "  /trade_off - Disable trading\n"
    guide += "\n📊 Simulation (Coming Soon):\n"
    guide += "  /simulate_match - Simulate a match\n"
    guide += "  /tournament_table - View standings\n"
    guide += "  /match_history - Past matches\n"
    guide += "  /update_tournament_stats - Merge auction results into stats\n"

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




@router.message(Command("help_all"))
async def help_all_command(message: Message) -> None:
    """Full admin help - DM only, admin only."""
    if message.chat.type != "private":
        await message.answer("This command can only be used in a private chat with the bot.")
        return
    if not message.from_user:
        return
    from app.bot.filters.admin import is_admin as _is_admin
    if not _is_admin(message.from_user.id):
        await message.answer("This command is only for admins.")
        return

    g = []
    g.append("ADMIN FULL GUIDE")
    g.append("=" * 24)
    g.append("")
    g.append("Everyone Commands")
    g.append("-" * 20)
    g.append("  /start - Open main menu")
    g.append("  /help - Show user commands")
    g.append("  /help_all - Show full admin guide (DM only)")
    g.append("  /cancel - Cancel current operation")
    g.append("  /teams - View all teams")
    g.append("  /my_team - View your team roster")
    g.append("  /purse - Check your team purse")
    g.append("  /team_logo - Upload team logo")
    g.append("  /bid <amount> - Place a bid")
    g.append("  /b <amount> - Place bid (short form)")
    g.append("  /trade_player - Trade player")
    g.append("  /accept_trade - Accept trade proposal")
    g.append("  /reject_trade - Reject trade proposal")
    g.append("  /add_coowner <team> - Add co-owner to team")
    g.append("  /remove_coowner <team> - Remove co-owner")
    g.append("  /player_photo <ID> - View/edit player photo")
    g.append("")
    g.append("Auction Commands")
    g.append("-" * 20)
    g.append("  /start_auction - Start auction for a set")
    g.append("  /pause_auction - Pause running auction")
    g.append("  /resume_auction - Resume paused auction")
    g.append("  /stop_auction - Stop running auction")
    g.append("  /next_player - Skip 15s inter-player delay")
    g.append("  /status - View auction status")
    g.append("")
    g.append("Team Management")
    g.append("-" * 20)
    g.append("  /create_tournament - Create a new tournament")
    g.append("  /complete_tournament - Complete/delete tournament")
    g.append("  /add_team - Add a new team")
    g.append("  /assign_owner - Assign owner to a team")
    g.append("  /edit_team - Edit team name or code")
    g.append("  /delete_team - Delete a team")
    g.append("  /change_owner - Change team owner")
    g.append("")
    g.append("Player Management")
    g.append("-" * 20)
    g.append("  /add_player - Add a new player")
    g.append("  /manual_sell - Manually sell player to team")
    g.append("  /manual_unsell - Remove player from team")
    g.append("  /player_photo <ID> - View/edit player photo")
    g.append("")
    g.append("Trade Control")
    g.append("-" * 20)
    g.append("  /trade_on - Enable player trading")
    g.append("  /trade_off - Disable player trading")
    g.append("")
    g.append("Match Simulation (Coming Soon)")
    g.append("-" * 20)
    g.append("  /simulate_match - Simulate a match between two teams")
    g.append("  /tournament_table - View tournament standings")
    g.append("  /match_history - View past matches")
    g.append("  /view_scorecard <id> - View match scorecard")
    g.append("  /refresh_stats - Fetch missing player stats from API")
    g.append("  /import_stats - Import player stats from CSV")
    g.append("  /update_tournament_stats - Merge auction results into stats")
    g.append("")
    g.append("Media Cache")
    g.append("-" * 20)
    g.append("  /player_image_change_generator - Cache player photos")
    g.append("  /image_change_generator - Upload GIF media files")
    g.append("  /upload_gif <key> - Upload a single GIF")
    g.append("  /save_all_media - Cache all media file IDs")
    g.append("")
    g.append("Admin Panel Buttons (in group)")
    g.append("-" * 20)
    g.append("  Players - View, import, search players")
    g.append("  Teams - Add, edit, delete teams, assign owners")
    g.append("  Tournaments - Create/manage tournaments")
    g.append("  Auction - Start, pause, resume, stop")
    g.append("  Manual Sell - Sell player to team")
    g.append("  Manual Unsell - Remove player from team")
    g.append("  Admin Management - Add/remove admins")
    g.append("  Co-owner Management - Add/remove co-owners")

    await message.answer("\n".join(g))


@router.message(Command("upload_gif"))
async def upload_gif_command(message: Message) -> None:
    """Upload a single GIF media file."""
    from app.bot.filters.admin import is_admin as _is_admin
    if not _is_admin(message.from_user.id):
        await message.answer("Only admins can use this command.")
        return
    if not message.reply_to_message or not (message.reply_to_message.animation or message.reply_to_message.video):
        await message.answer("Reply to a GIF/video with /upload_gif <key>\n\nValid keys: bid1, bid2, bid3, bid4, once, twice, sold, unsold")
        return
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer("Usage: /upload_gif <key>\n\nValid keys: bid1, bid2, bid3, bid4, once, twice, sold, unsold")
        return
    key = parts[1].lower()
    valid_keys = {"bid1", "bid2", "bid3", "bid4", "once", "twice", "sold", "unsold"}
    if key not in valid_keys:
        await message.answer(f"Invalid key: {key}\nValid keys: {', '.join(sorted(valid_keys))}")
        return
    media = message.reply_to_message.animation or message.reply_to_message.video
    if not media:
        await message.answer("No media found in the replied message.")
        return
    file_id = media.file_id
    unique_id = media.file_unique_id
    media_type = "animation" if message.reply_to_message.animation else "video"
    from app.bot.handlers.auction import _save_media_to_db
    local_map = {
        "bid1": "data/bid1.gif", "bid2": "data/bid2.gif",
        "bid3": "data/bid3.gif", "bid4": "data/bid4.gif",
        "once": "data/once.jpg", "twice": "data/twice.jpg",
        "sold": "data/sold.gif", "unsold": "data/unsold.gif",
    }
    await _save_media_to_db(key, file_id, unique_id, local_map.get(key), media_type)
    await message.answer(f"Saved {key}: file_id={file_id[:30]}...")


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
