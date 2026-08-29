"""Add admin panel buttons and auto-generate player IDs."""

import os

# ============================================================
# 1. Remove Upload Photos from admin panel keyboard + handlers
# ============================================================
with open("app/bot/keyboards/home.py", "r", encoding="utf-8") as f:
    home = f.read()

# Remove upload photos button from admin_panel_keyboard
home = home.replace(
    '        [\n            InlineKeyboardButton(text="\\U0001f4f7 Upload Photos", callback_data="admin:players_upload"),\n            InlineKeyboardButton(text="\\U0001f46e Manage Admins", callback_data="admin:manage_admins"),\n        ],',
    '        [\n            InlineKeyboardButton(text="\\U0001f46e Manage Admins", callback_data="admin:manage_admins"),\n        ],',
)

# Add new admin sub-panel keyboards
new_keyboards = '''


def admin_teams_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton(text="\\U0001f3cf Add Team", callback_data="admin:teams:add")],
        [InlineKeyboardButton(text="\\U0001f464 Assign Owner", callback_data="admin:teams:assign")],
        [InlineKeyboardButton(text="\\u2b05\\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_tournament_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton(text="\\U0001f3c6 Create Tournament", callback_data="admin:tournaments:create")],
        [InlineKeyboardButton(text="\\u270f\\ufe0f Edit Tournament", callback_data="admin:tournaments:edit")],
        [InlineKeyboardButton(text="\\u2b05\\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_auction_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton(text="\\U0001f534 Start Auction", callback_data="admin:auction:start")],
        [InlineKeyboardButton(text="\\u23f8\\ufe0f Pause", callback_data="admin:auction:pause"),
         InlineKeyboardButton(text="\\u25b6\\ufe0f Resume", callback_data="admin:auction:resume")],
        [InlineKeyboardButton(text="\\u23f9\\ufe0f Stop", callback_data="admin:auction:stop")],
        [InlineKeyboardButton(text="\\u2139\\ufe0f Status", callback_data="admin:auction:status")],
        [InlineKeyboardButton(text="\\u2b05\\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
'''

# Replace the old admin_players_keyboard and admin_manage_keyboard
home = home.rstrip() + new_keyboards

with open("app/bot/keyboards/home.py", "w", encoding="utf-8") as f:
    f.write(home)
print("home keyboards updated")


# ============================================================
# 2. Update admin panel handlers in start.py
# ============================================================
with open("app/bot/handlers/start.py", "r", encoding="utf-8") as f:
    start = f.read()

# Replace admin:teams handler with button panel
old_teams = '''@router.callback_query(F.data == "admin:teams")
async def admin_teams_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin access is required.", show_alert=True)
        return
    await callback.message.answer("\\U0001f3cf /add_team -- /assign_owner")
    await callback.answer()'''

new_teams = '''@router.callback_query(F.data == "admin:teams")
async def admin_teams_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("\\U0001f6e1\\ufe0f Admin access required.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_teams_keyboard
    await callback.message.answer("\\U0001f3cf Team Management", reply_markup=admin_teams_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin:teams:add")
async def admin_teams_add(callback: CallbackQuery) -> None:
    await callback.message.answer("\\U0001f3cf Use /add_team in the group")
    await callback.answer()

@router.callback_query(F.data == "admin:teams:assign")
async def admin_teams_assign(callback: CallbackQuery) -> None:
    await callback.message.answer("\\U0001f464 Reply to the owner message with /assign_owner CSK")
    await callback.answer()'''

start = start.replace(old_teams, new_teams)

# Replace admin:tournaments handler with button panel
old_tournaments = '''@router.callback_query(F.data == "admin:tournaments")
async def admin_tournaments_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin access is required.", show_alert=True)
        return
    await callback.message.answer("\\U0001f3c6 Use /create_tournament to create a new tournament.")
    await callback.answer()'''

new_tournaments = '''@router.callback_query(F.data == "admin:tournaments")
async def admin_tournaments_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("\\U0001f6e1\\ufe0f Admin access required.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_tournament_keyboard
    await callback.message.answer("\\U0001f3c6 Tournament Management", reply_markup=admin_tournament_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin:tournaments:create")
async def admin_tournaments_create(callback: CallbackQuery) -> None:
    await callback.message.answer("\\U0001f3c6 Use /create_tournament in the group")
    await callback.answer()

@router.callback_query(F.data == "admin:tournaments:edit")
async def admin_tournaments_edit(callback: CallbackQuery) -> None:
    await callback.message.answer("\\u270f\\ufe0f Create a tournament first, then use the edit buttons during creation.")
    await callback.answer()'''

start = start.replace(old_tournaments, new_tournaments)

# Replace admin:auction handler with button panel
old_auction = '''@router.callback_query(F.data == "admin:auction")
async def admin_auction_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin access is required.", show_alert=True)
        return
    await callback.message.answer(
        "\\U0001f4b0 Auction commands:\\n\\n"
        "/start_auction - Start auction\\n"
        "/pause_auction - Pause\\n"
        "/resume_auction - Resume\\n"
        "/stop_auction - Stop\\n"
        "/status - View status"
    )
    await callback.answer()'''

new_auction = '''@router.callback_query(F.data == "admin:auction")
async def admin_auction_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("\\U0001f6e1\\ufe0f Admin access required.", show_alert=True)
        return
    from app.bot.keyboards.home import admin_auction_keyboard
    await callback.message.answer("\\U0001f4b0 Auction Control", reply_markup=admin_auction_keyboard())
    await callback.answer()

@router.callback_query(F.data == "admin:auction:start")
async def admin_auction_start_btn(callback: CallbackQuery) -> None:
    await callback.message.answer("\\U0001f534 Use /start_auction in the group")
    await callback.answer()

@router.callback_query(F.data == "admin:auction:pause")
async def admin_auction_pause_btn(callback: CallbackQuery) -> None:
    await callback.message.answer("\\u23f8\\ufe0f Use /pause_auction in the group")
    await callback.answer()

@router.callback_query(F.data == "admin:auction:resume")
async def admin_auction_resume_btn(callback: CallbackQuery) -> None:
    await callback.message.answer("\\u25b6\\ufe0f Use /resume_auction in the group")
    await callback.answer()

@router.callback_query(F.data == "admin:auction:stop")
async def admin_auction_stop_btn(callback: CallbackQuery) -> None:
    await callback.message.answer("\\u23f9\\ufe0f Use /stop_auction in the group")
    await callback.answer()

@router.callback_query(F.data == "admin:auction:status")
async def admin_auction_status_btn(callback: CallbackQuery) -> None:
    await callback.message.answer("\\u2139\\ufe0f Use /status in the group")
    await callback.answer()'''

start = start.replace(old_auction, new_auction)

with open("app/bot/handlers/start.py", "w", encoding="utf-8") as f:
    f.write(start)
print("start handlers updated")


# ============================================================
# 3. Auto-generate player IDs in players_admin.py
# ============================================================
with open("app/bot/handlers/players_admin.py", "r", encoding="utf-8") as f:
    pa = f.read()

# Replace the add player flow - remove the player_id input step
# Instead auto-generate PLY + next number
old_add_start = '''@router.callback_query(F.data == "admin:players:add")
async def admin_players_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Admin access is required.", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminPlayerStates.waiting_for_player_id)
    await callback.message.answer("Enter the player ID (e.g., PLY0001):")
    await callback.answer()'''

new_add_start = '''@router.callback_query(F.data == "admin:players:add")
async def admin_players_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("\\U0001f6e1\\ufe0f Admin access required.", show_alert=True)
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
    await callback.message.answer(f"\\U0001f464 New player ID: {new_id}\\n\\nEnter the player name:")
    await callback.answer()'''

pa = pa.replace(old_add_start, new_add_start)

# Remove the waiting_for_player_id handler since ID is auto-generated
old_id_handler = '''@router.message(AdminPlayerStates.waiting_for_player_id)
async def add_player_id(message: Message, state: FSMContext) -> None:
    pid = (message.text or "").strip()
    async with AsyncSessionLocal() as session:
        exists = await session.scalar(select(Player).where(Player.player_id == pid))
    if exists:
        await message.answer(f"Player {pid} already exists. Enter a different ID:")
        return
    await state.update_data(player_id=pid)
    await state.set_state(AdminPlayerStates.waiting_for_name)
    await message.answer("Enter the player name:")'''

new_id_handler = '''@router.message(AdminPlayerStates.waiting_for_player_id)
async def add_player_id(message: Message, state: FSMContext) -> None:
    # This state is no longer used - ID is auto-generated
    await state.set_state(AdminPlayerStates.waiting_for_name)
    await message.answer("Enter the player name:")'''

pa = pa.replace(old_id_handler, new_id_handler)

# Add emojis to add player messages
pa = pa.replace('"Enter the player name:"', '"\\U0001f464 Enter the player name:"')
pa = pa.replace('"Enter the country:"', '"\\U0001f30d Enter the country:"')
pa = pa.replace('"Enter the role (e.g., Batsman, Bowler, All-rounder, Wicketkeeper):"', '"\\U0001f3cf Role (Batsman/Bowler/All-rounder/Wicketkeeper):"')
pa = pa.replace('"Is this player overseas? (yes/no):"', '"\\u2708\\ufe0f Overseas? (yes/no):"')
pa = pa.replace('"Enter the set number:"', '"\\U0001f3c6 Set number:"')
pa = pa.replace('"Enter the base price in Cr (e.g., 2.00):"', '"\\U0001f4b0 Base price in Cr (e.g. 2.00):"')
pa = pa.replace('"Player added!"', '"\\u2705 Player added!"')
pa = pa.replace('"Editing {player.name} ({pid})\\\\nSelect field to edit:"', '"\\u270f\\ufe0f Editing {player.name} ({pid})\\\\nSelect field:"')
pa = pa.replace('"Enter the new value for {field}:"', '"\\u270f\\ufe0f New value for {field}:"')
pa = pa.replace('"Updated {field} to {value} for {player.name}."', '"\\u2705 Updated {field} for {player.name}."')
pa = pa.replace('"Delete {player.name} ({pid})? This cannot be undone.\\\\nType yes to confirm:"', '"\\u2796 Delete {player.name} ({pid})?\\\\nType yes to confirm:"')
pa = pa.replace('"Deleted {player.name} ({player.player_id})."', '"\\u2705 Deleted {player.name}."')
pa = pa.replace('"Deletion cancelled."', '"\\u274c Cancelled."')
pa = pa.replace('"Player not found."', '"\\u274c Player not found."')
pa = pa.replace('"No player found with ID: {player_id_text}"', '"\\u274c No player: {player_id_text}"')
pa = pa.replace('"Saved file_id for {player.name} ({player.player_id})"', '"\\u2705 Saved file_id for {player.name}"')
pa = pa.replace('"Swap Confirmation:"', '"\\U0001f504 Swap Confirmation:"')
pa = pa.replace('"Swap completed!"', '"\\u2705 Swap completed!"')
pa = pa.replace('"Swap failed: player not found in auction results."', '"\\u274c Swap failed: player not found."')
pa = pa.replace('"Swap cancelled."', '"\\u274c Swap cancelled."')
pa = pa.replace('"No other teams to swap with."', '"\\u274c No other teams."')
pa = pa.replace('"You have no players to swap."', '"\\u274c No players to swap."')

with open("app/bot/handlers/players_admin.py", "w", encoding="utf-8") as f:
    f.write(pa)
print("players_admin updated")
