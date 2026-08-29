"""Add admin player management and keyboard helpers."""

# 1. Add admin_player_list_keyboard to home.py
with open("app/bot/keyboards/home.py", "r", encoding="utf-8") as f:
    home = f.read()

admin_player_list_kb = '''

def admin_player_list_keyboard(page, total, page_size):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="Prev", callback_data=f"admin:players:page:{page-1}"))
    if (page + 1) * page_size < total:
        nav.append(InlineKeyboardButton(text="Next", callback_data=f"admin:players:page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Back", callback_data="admin:players")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
'''

home = home.rstrip() + admin_player_list_kb

with open("app/bot/keyboards/home.py", "w", encoding="utf-8") as f:
    f.write(home)
print("home.py updated")

# 2. Add AdminPlayerStates to auction_states.py
with open("app/bot/states/auction_states.py", "r", encoding="utf-8") as f:
    states = f.read()

if "AdminPlayerStates" not in states:
    states += '''

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
'''

with open("app/bot/states/auction_states.py", "w", encoding="utf-8") as f:
    f.write(states)
print("states updated")

# 3. Add admin player management handlers to start.py
with open("app/bot/handlers/start.py", "r", encoding="utf-8") as f:
    start = f.read()

# Add import for AdminPlayerStates
if "AdminPlayerStates" not in start:
    start = start.replace(
        "from app.bot.keyboards.home import (",
        "from app.bot.states.auction_states import AdminPlayerStates\nfrom app.bot.keyboards.home import ("
    )

# Add handlers before the help section
help_idx = start.find("# --- help")
if help_idx == -1:
    help_idx = start.find("send_help")

new_handlers = '''
# -- admin player view --

@router.callback_query(F.data == "admin:players:view")
async def admin_players_view(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin access is required.", show_alert=True)
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
    text = f"Players (Page {page + 1}/{(total + page_size - 1) // page_size})\\n\\n"
    text += "\\n".join(f"{p.player_id} | {p.name}" for p in players)
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
        await callback.answer("Admin access is required.", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminPlayerStates.waiting_for_player_id)
    await callback.message.answer("Enter the player ID (e.g., PLY0001):")
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
        f"Player added!\\n\\nID: {data['player_id']}\\n"
        f"Name: {data['name']}\\nCountry: {data['country']}\\n"
        f"Role: {data['role']}\\nOverseas: {data['is_overseas']}\\n"
        f"Set: {data['set_number']}\\nBase Price: Rs.{bp:.2f} Cr"
    )

# -- admin player edit --

@router.callback_query(F.data == "admin:players:edit")
async def admin_players_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin access is required.", show_alert=True)
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
    await message.answer(f"Editing {player.name} ({pid})\\nSelect field to edit:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
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
        await callback.answer("Admin access is required.", show_alert=True)
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
    await message.answer(f"Delete {player.name} ({pid})? This cannot be undone.\\nType yes to confirm:")

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
    await callback.message.answer("Reply to the user message with /add_admin\\nor use /add_admin <user_id>")
    await callback.answer()

@router.callback_query(F.data == "admin:manage:remove")
async def admin_manage_remove_button(callback: CallbackQuery) -> None:
    await callback.message.answer("Use /remove_admin <user_id>")
    await callback.answer()

@router.callback_query(F.data == "admin:manage:list")
async def admin_manage_list_button(callback: CallbackQuery) -> None:
    from app.services.admin_service import get_admin_ids as get_all_admin_ids
    admins = get_all_admin_ids()
    lines = ["  - " + str(aid) for aid in sorted(admins)]
    admin_list = chr(10).join(lines)
    await callback.message.answer("Current admins:" + chr(10) + admin_list)
    await callback.answer()


'''

# Insert before send_help
insert_idx = start.find("async def send_help")
if insert_idx == -1:
    print("Could not find send_help")
else:
    start = start[:insert_idx] + new_handlers + start[insert_idx:]

with open("app/bot/handlers/start.py", "w", encoding="utf-8") as f:
    f.write(start)
print("start.py updated")
