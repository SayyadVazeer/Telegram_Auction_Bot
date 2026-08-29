"""Fix remaining 3 issues: auto-gen IDs, single bid button, /bid live edit."""

# === Fix 1: Auto-generate player IDs in start.py ===
with open("app/bot/handlers/start.py", "r", encoding="utf-8") as f:
    start = f.read()

# Find admin_players_add_start handler and replace it
old_add = """@router.callback_query(F.data == \"admin:players:add\")
async def admin_players_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(\"\\u274c Admin access required.\", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminPlayerStates.waiting_for_player_id)
    await callback.message.answer(\"Enter the player ID (e.g., PLY0001):\")
    await callback.answer()"""

new_add = """@router.callback_query(F.data == \"admin:players:add\")
async def admin_players_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer(\"\\u274c Admin access required.\", show_alert=True)
        return
    # Auto-generate next player ID
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player.player_id).order_by(Player.id.desc()).limit(1))
        last_id = result.scalar()
        if last_id and last_id.startswith(\"PLY\"):
            num = int(last_id[3:]) + 1
        else:
            num = 1
        new_id = f\"PLY{num:04d}\"
    await state.clear()
    await state.update_data(player_id=new_id)
    await state.set_state(AdminPlayerStates.waiting_for_name)
    await callback.message.answer(f\"\\U0001f464 New player ID: {new_id}\\n\\nEnter the player name:\\nUse /cancel to cancel.\")
    await callback.answer()"""

start = start.replace(old_add, new_add)

with open("app/bot/handlers/start.py", "w", encoding="utf-8") as f:
    f.write(start)
print("Fix 1: Auto-generate player IDs")


# === Fix 2: Single bid button in auction.py keyboard ===
with open("app/bot/keyboards/auction.py", "r", encoding="utf-8") as f:
    ak = f.read()

# Use a targeted approach - find the two button rows and replace
import re

# Find the bid_increment buttons pattern and replace with single
pattern = r'(\[\s*\n\s*InlineKeyboardButton\(\s*text=f"\\U0001f528 \+\\{increment:\\.2f\\}",\s*callback_data=f"auction:bid_increment:\\{increment:\\.2f\\}",\s*\),\s*\n\s*InlineKeyboardButton\(\s*text=f"\\U0001f528 \+\\{second_increment:\\.2f\\}",\s*callback_data=f"auction:bid_increment:\\{second_increment:\\.2f\\}",\s*\),\s*\n\s*\],)'
replacement = '[\n            InlineKeyboardButton(\n                text=f"\\U0001f528 Bid +{increment:.2f}",\n                callback_data=f"auction:bid_increment:{increment:.2f}",\n            ),\n        ],'

# Just do a simple text replace for the two buttons
old_bid = '''            InlineKeyboardButton(
                text=f\"\\U0001f528 +{increment:.2f}\",
                callback_data=f\"auction:bid_increment:{increment:.2f}\",
            ),
            InlineKeyboardButton(
                text=f\"\\U0001f528 +{second_increment:.2f}\",
                callback_data=f\"auction:bid_increment:{second_increment:.2f}\",
            ),'''

new_bid = '''            InlineKeyboardButton(
                text=f\"\\U0001f528 Bid +{increment:.2f}\",
                callback_data=f\"auction:bid_increment:{increment:.2f}\",
            ),'''

ak = ak.replace(old_bid, new_bid)

# Remove second_increment line
ak = ak.replace('    second_increment = increment * 2\n', '')

with open("app/bot/keyboards/auction.py", "w", encoding="utf-8") as f:
    f.write(ak)
print("Fix 2: Single bid button in auction.py")


# === Fix 3: Verify /bid live edit ===
with open("app/bot/handlers/bidding.py", "r", encoding="utf-8") as f:
    bidding = f.read()

if 'edit_message_caption' in bidding:
    print("Fix 3: /bid live edit already present")
else:
    print("Fix 3: /bid live edit MISSING - needs manual fix")
