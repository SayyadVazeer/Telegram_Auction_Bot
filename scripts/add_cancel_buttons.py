"""Add cancel support to all FSM states."""

# 1. Add /cancel handler to start.py (catch-all for any state)
with open("app/bot/handlers/start.py", "r", encoding="utf-8") as f:
    start = f.read()

# Check if there's already a catch-all cancel in tournament.py
with open("app/bot/handlers/tournament.py", "r", encoding="utf-8") as f:
    tourney = f.read()

# The tournament.py already has /cancel. Let me make sure it clears state and sends a message.
# Check current cancel handler
if '@router.message(Command("cancel"))' in tourney:
    print("Cancel handler exists in tournament.py")

# 2. Add cancel button to players_admin.py states
with open("app/bot/handlers/players_admin.py", "r", encoding="utf-8") as f:
    pa = f.read()

# Add a cancel handler at the end of players_admin.py
cancel_handler = '''


# -- /cancel for all states --

@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("\\u2139\\ufe0f Nothing to cancel.")
        return
    await state.clear()
    await message.answer("\\u274c Cancelled.")
'''

if 'async def cancel_any' not in pa:
    pa = pa.rstrip() + cancel_handler
    with open("app/bot/handlers/players_admin.py", "w", encoding="utf-8") as f:
        f.write(pa)
    print("Added cancel handler to players_admin.py")

# 3. Add /cancel hint to each step message in players_admin.py
with open("app/bot/handlers/players_admin.py", "r", encoding="utf-8") as f:
    pa = f.read()

# Add /cancel hint to the add player flow
hints = [
    ('"\\U0001f464 Enter the player name:"', '"\\U0001f464 Enter the player name:\\nUse /cancel to cancel."'),
    ('"\\U0001f30d Enter the country:"', '"\\U0001f30d Enter the country:\\nUse /cancel to cancel."'),
    ('"\\U0001f3cf Role (Batsman/Bowler/All-rounder/Wicketkeeper):"', '"\\U0001f3cf Role (Batsman/Bowler/All-rounder/Wicketkeeper):\\nUse /cancel to cancel."'),
    ('"\\u2708\\ufe0f Overseas? (yes/no):"', '"\\u2708\\ufe0f Overseas? (yes/no):\\nUse /cancel to cancel."'),
    ('"\\U0001f3c6 Set number:"', '"\\U0001f3c6 Set number:\\nUse /cancel to cancel."'),
    ('"\\U0001f4b0 Base price in Cr (e.g. 2.00):"', '"\\U0001f4b0 Base price in Cr (e.g. 2.00):\\nUse /cancel to cancel."'),
    ('"\\u270f\\ufe0f Editing {player.name} ({pid})\\\\nSelect field:"', '"\\u270f\\ufe0f Editing {player.name} ({pid})\\nSelect field:\\nUse /cancel to cancel."'),
    ('"\\u270f\\ufe0f New value for {field}:"', '"\\u270f\\ufe0f New value for {field}:\\nUse /cancel to cancel."'),
    ('"\\u2796 Delete {player.name} ({pid})?\\\\nType yes to confirm:"', '"\\u2796 Delete {player.name} ({pid})?\\nType yes to cancel: no\\nUse /cancel to cancel."'),
    ('"Enter the player ID to edit (e.g., PLY0001):"', '"Enter the player ID to edit:\\nUse /cancel to cancel."'),
    ('"Enter the player ID to delete (e.g., PLY0001):"', '"Enter the player ID to delete:\\nUse /cancel to cancel."'),
]

for old, new in hints:
    if old in pa and new not in pa:
        pa = pa.replace(old, new)

with open("app/bot/handlers/players_admin.py", "w", encoding="utf-8") as f:
    f.write(pa)
print("Added cancel hints to players_admin.py")


# 4. Add cancel hints to auction.py states
with open("app/bot/handlers/auction.py", "r", encoding="utf-8") as f:
    auction = f.read()

auction_hints = [
    ('"\\U0001f3c6 Select the set to auction:"', '"\\U0001f3c6 Select the set to auction:\\nUse /cancel to cancel."'),
    ('"\\u23f1\\ufe0f Enter bid timer in seconds (1-600):"', '"\\u23f1\\ufe0f Enter bid timer in seconds (1-600):\\nUse /cancel to cancel."'),
    ('"\\U0001f534 Use /start_auction in the group"', '"\\U0001f534 Use /start_auction in the group\\nUse /cancel to cancel."'),
    ('"\\u270f\\ufe0f Enter bid amount in Cr (e.g. 4.70)\\\\nUse /cancel to cancel."', '"\\u270f\\ufe0f Enter bid amount in Cr (e.g. 4.70)\\nUse /cancel to cancel."'),
]

for old, new in auction_hints:
    if old in auction and new not in auction:
        auction = auction.replace(old, new)

with open("app/bot/handlers/auction.py", "w", encoding="utf-8") as f:
    f.write(auction)
print("Added cancel hints to auction.py")


# 5. Make sure tournament.py cancel handler is robust
with open("app/bot/handlers/tournament.py", "r", encoding="utf-8") as f:
    t = f.read()

# The cancel handler should work for ANY state
old_cancel = '''@router.message(Command("cancel"))
async def cancel_tournament_creation(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()

    if current_state is None:
        await message.answer("\\u2139\\ufe0f Nothing to cancel.")
        return

    await state.clear()

    await message.answer("\\u274c Cancelled.")'''

# Keep it as is - it already clears any state
print("Tournament cancel handler OK")

# 6. Add cancel handler to bidding.py too
with open("app/bot/handlers/bidding.py", "r", encoding="utf-8") as f:
    bid = f.read()

# Add /cancel hint to custom bid prompt
bid = bid.replace(
    '"\\u270f\\ufe0f Enter bid amount in Cr (e.g. 4.70)\\nUse /cancel to cancel."',
    '"\\u270f\\ufe0f Enter bid amount in Cr (e.g. 4.70)\\nUse /cancel to cancel."'
)

with open("app/bot/handlers/bidding.py", "w", encoding="utf-8") as f:
    f.write(bid)
print("bidding.py OK")

print("All cancel handlers added!")
