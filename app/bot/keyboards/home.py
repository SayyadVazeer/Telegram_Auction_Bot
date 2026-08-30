"""All keyboard layouts for the bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from decimal import Decimal


def home_keyboard(*, is_admin: bool, is_owner: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="👥 Players", callback_data="home:players"),
            InlineKeyboardButton(text="🏏 Teams", callback_data="home:teams"),
        ],
        [
            InlineKeyboardButton(text="🏆 Tournament", callback_data="home:tournament"),
            InlineKeyboardButton(text="❓ Help", callback_data="home:help"),
        ],
    ]
    if is_owner:
        rows.append([InlineKeyboardButton(text="🙋 My Team", callback_data="home:my_team")])
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠️ Admin panel", callback_data="home:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="👥 Players", callback_data="admin:players"),
            InlineKeyboardButton(text="🏏 Teams", callback_data="admin:teams"),
        ],
        [
            InlineKeyboardButton(text="🏆 Tournaments", callback_data="admin:tournaments"),
            InlineKeyboardButton(text="💰 Auction", callback_data="admin:auction"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_players_keyboard():
    rows = [
        [InlineKeyboardButton(text="👁️ View Players", callback_data="admin:players:view")],
        [InlineKeyboardButton(text="➕ Add Player", callback_data="admin:players:add")],
        [InlineKeyboardButton(text="✏️ Edit Player", callback_data="admin:players:edit")],
        [InlineKeyboardButton(text="➖ Delete Player", callback_data="admin:players:delete")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_teams_keyboard():
    rows = [
        [InlineKeyboardButton(text="➕ Add Team", callback_data="admin:teams:add")],
        [InlineKeyboardButton(text="👤 Assign Owner", callback_data="admin:teams:assign")],
        [InlineKeyboardButton(text="✏️ Edit Team", callback_data="admin:teams:edit")],
        [InlineKeyboardButton(text="🗑️ Delete Team", callback_data="admin:teams:delete")],
        [InlineKeyboardButton(text="🔄 Change Owner", callback_data="admin:teams:change_owner")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_tournament_keyboard():
    rows = [
        [InlineKeyboardButton(text="🏆 Create Tournament", callback_data="admin:tournaments:create")],
        [InlineKeyboardButton(text="✏️ Edit Tournament", callback_data="admin:tournaments:edit")],
        [InlineKeyboardButton(text="❌ Complete Tournament", callback_data="admin:tournaments:complete")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_auction_keyboard():
    rows = [
        [InlineKeyboardButton(text="🔴 Start Auction", callback_data="admin:auction:start")],
        [InlineKeyboardButton(text="⏸️ Pause", callback_data="admin:auction:pause"),
         InlineKeyboardButton(text="▶️ Resume", callback_data="admin:auction:resume")],
        [InlineKeyboardButton(text="⏹️ Stop", callback_data="admin:auction:stop")],
        [InlineKeyboardButton(text="ℹ️ Status", callback_data="admin:auction:status")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_manage_keyboard():
    rows = [
        [InlineKeyboardButton(text="➕ Add Admin", callback_data="admin:manage:add")],
        [InlineKeyboardButton(text="➖ Remove Admin", callback_data="admin:manage:remove")],
        [InlineKeyboardButton(text="📋 List Admins", callback_data="admin:manage:list")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_player_alphabet_keyboard():
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rows = [
        [
            InlineKeyboardButton(text=letter, callback_data=f"admin:players:letter:{letter}")
            for letter in letters[i:i + 6]
        ]
        for i in range(0, len(letters), 6)
    ]
    rows.append([InlineKeyboardButton(text="Back", callback_data="admin:players")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_player_letter_keyboard(letter, page, total, page_size):
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="Prev", callback_data=f"admin:players:page:{letter}:{page-1}"))
    if (page + 1) * page_size < total:
        nav.append(InlineKeyboardButton(text="Next", callback_data=f"admin:players:page:{letter}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Letters", callback_data="admin:players:view")])
    rows.append([InlineKeyboardButton(text="Back", callback_data="admin:players")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_player_list_keyboard(page, total, page_size):
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin:players:page:{page-1}"))
    if (page + 1) * page_size < total:
        nav.append(InlineKeyboardButton(text="➡️ Next", callback_data=f"admin:players:page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin:players")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def players_filter_keyboard() -> InlineKeyboardMarkup:
    """Show player filter options: All, Sold, Unsold before alphabet."""
    rows = [
        [
            InlineKeyboardButton(text="📋 All Players", callback_data="players:filter:all"),
            InlineKeyboardButton(text="✅ Sold", callback_data="players:filter:sold"),
        ],
        [
            InlineKeyboardButton(text="❌ Unsold", callback_data="players:filter:unsold"),
            InlineKeyboardButton(text="⏸️ Not Participated", callback_data="players:filter:not_participated"),
        ],
        [
            InlineKeyboardButton(text="🔤 Browse by Letter", callback_data="players:filter:alphabet"),
        ],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alphabet_keyboard(*, filter_mode: str = "all") -> InlineKeyboardMarkup:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rows = [
        [
            InlineKeyboardButton(
                text=letter,
                callback_data=f"players:letter:{filter_mode}:{letter}",
            )
            for letter in letters[index : index + 6]
        ]
        for index in range(0, len(letters), 6)
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="players:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filtered_player_list_keyboard(
    filter_mode: str,
    letter: str | None,
    page: int,
    total_players: int,
    *,
    page_size: int = 10,
    players: list = None,
) -> InlineKeyboardMarkup:
    rows = []
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=f"players:page:{filter_mode}:{letter or '_'}:{page - 1}",
            )
        )
    if (page + 1) * page_size < total_players:
        navigation.append(
            InlineKeyboardButton(
                text="➡️ Next",
                callback_data=f"players:page:{filter_mode}:{letter or '_'}:{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="players:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def player_list_keyboard(
    letter: str,
    page: int,
    total_players: int,
    *,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    """Backward-compatible wrapper using new filtered keyboard."""
    return filtered_player_list_keyboard("all", letter, page, total_players, page_size=page_size)


# ── Auction keyboards ───────────────────────────────────────────

def auction_keyboard(
    minimum_increment: Decimal | None = None,
    *,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    increment = minimum_increment or Decimal("0.50")
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔨 +{increment:.2f}",
                callback_data=f"auction:bid_increment:{increment:.2f}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data="auction:refresh",
            ),
        ],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(text="⏸️ Pause", callback_data="auction:pause"),
                InlineKeyboardButton(text="▶️ Resume", callback_data="auction:resume"),
                InlineKeyboardButton(text="⏹️ Stop", callback_data="auction:stop"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_selection_keyboard(set_numbers: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(set_numbers), 4):
        row = [
            InlineKeyboardButton(text=str(snum), callback_data=f"auction:set:{snum}")
            for snum in set_numbers[i:i+4]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="auction:cancel_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_keyboard(set_number: int, pending_count: int, unsold_count: int) -> InlineKeyboardMarkup:
    rows = []
    if pending_count > 0:
        rows.append([
            InlineKeyboardButton(
                text=f"🟢 Pending ({pending_count})",
                callback_data=f"auction:cat:pending:{set_number}",
            )
        ])
    if unsold_count > 0:
        rows.append([
            InlineKeyboardButton(
                text=f"🟡 Unsold ({unsold_count})",
                callback_data=f"auction:cat:unsold:{set_number}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="auction:cancel_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timer_keyboard(set_number: int, category: str) -> InlineKeyboardMarkup:
    rows = []
    for secs in [15, 20, 30, 45, 60]:
        rows.append([
            InlineKeyboardButton(
                text=f"⏱️ {secs}s",
                callback_data=f"auction:timer:{set_number}:{category}:{secs}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="⏰ Custom",
            callback_data=f"auction:timer:custom:{set_number}:{category}",
        )
    ])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="auction:cancel_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── Trade keyboards ──────────────────────────────────────

def trade_player_keyboard(players: list) -> InlineKeyboardMarkup:
    """Show player buttons for trade selection."""
    rows = []
    for r, p in players:
        rows.append([
            InlineKeyboardButton(
                text=f"{p.player_id} | {p.name} {'✈️' if p.is_overseas else ''} | Rs.{Decimal(str(r.final_bid_cr)):.2f} Cr",
                callback_data=f"trade:player:{p.player_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="trade:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_team_keyboard(teams: list) -> InlineKeyboardMarkup:
    """Show team buttons for trade selection."""
    rows = []
    for t in teams:
        rows.append([
            InlineKeyboardButton(
                text=f"{t.short_code} | {t.name}",
                callback_data=f"trade:team:{t.short_code}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="trade:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_confirm_keyboard() -> InlineKeyboardMarkup:
    """Show confirm/cancel buttons for trade."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Confirm Trade", callback_data="trade:confirm"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="trade:cancel"),
        ]
    ])


def trade_action_keyboard() -> InlineKeyboardMarkup:
    """Show accept/reject buttons for incoming trade."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Accept Trade", callback_data="trade:accept"),
            InlineKeyboardButton(text="🚫 Reject Trade", callback_data="trade:reject"),
        ]
    ])


def trade_admin_keyboard() -> InlineKeyboardMarkup:
    """Show approve/reject buttons for admin trade approval."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve Trade", callback_data="trade:admin_approve"),
            InlineKeyboardButton(text="❌ Reject Trade", callback_data="trade:admin_reject"),
        ]
    ])


# -- Manual Sell/Unsell keyboards --

def manual_sell_team_keyboard(teams: list) -> InlineKeyboardMarkup:
    """Show team buttons for manual sell selection."""
    rows = []
    for t in teams:
        rows.append([
            InlineKeyboardButton(
                text=f"🏏 {t.short_code} | {t.name}",
                callback_data=f"msell:team:{t.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="admin:auction")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_sell_player_keyboard(team_id: int, players: list) -> InlineKeyboardMarkup:
    """Show player buttons within a team for manual sell."""
    rows = []
    for p in players:
        overseas = " ✈️" if p.is_overseas else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{p.player_id} | {p.name}{overseas}",
                callback_data=f"msell:player:{team_id}:{p.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin:manual_sell")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_unsell_team_keyboard(teams: list) -> InlineKeyboardMarkup:
    """Show team buttons for manual unsell selection."""
    rows = []
    for t in teams:
        rows.append([
            InlineKeyboardButton(
                text=f"🏏 {t.short_code} | {t.name}",
                callback_data=f"munsell:team:{t.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="admin:auction")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_unsell_player_keyboard(team_id: int, players: list) -> InlineKeyboardMarkup:
    """Show player buttons within a team for manual unsell."""
    rows = []
    for p in players:
        overseas = " ✈️" if p.is_overseas else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{p.player_id} | {p.name}{overseas}",
                callback_data=f"munsell:player:{team_id}:{p.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin:manual_unsell")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

