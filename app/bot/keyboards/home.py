"""All keyboard layouts for the bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from decimal import Decimal


def home_keyboard(*, is_admin: bool, is_owner: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="\U0001f465 Players", callback_data="home:players"),
            InlineKeyboardButton(text="\U0001f3cf Teams", callback_data="home:teams"),
        ],
        [
            InlineKeyboardButton(text="\U0001f3c6 Tournament", callback_data="home:tournament"),
            InlineKeyboardButton(text="\u2753 Help", callback_data="home:help"),
        ],
    ]
    if is_owner:
        rows.append([InlineKeyboardButton(text="\U0001f64b My Team", callback_data="home:my_team")])
    if is_admin:
        rows.append([InlineKeyboardButton(text="\U0001f6e0\ufe0f Admin panel", callback_data="home:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="\U0001f465 Players", callback_data="admin:players"),
            InlineKeyboardButton(text="\U0001f3cf Teams", callback_data="admin:teams"),
        ],
        [
            InlineKeyboardButton(text="\U0001f3c6 Tournaments", callback_data="admin:tournaments"),
            InlineKeyboardButton(text="\U0001f4b0 Auction", callback_data="admin:auction"),
        ],
        [
            InlineKeyboardButton(text="\U0001f46e Manage Admins", callback_data="admin:manage_admins"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_players_keyboard():
    rows = [
        [InlineKeyboardButton(text="\U0001f441\ufe0f View Players", callback_data="admin:players:view")],
        [InlineKeyboardButton(text="\u2795 Add Player", callback_data="admin:players:add")],
        [InlineKeyboardButton(text="\u270f\ufe0f Edit Player", callback_data="admin:players:edit")],
        [InlineKeyboardButton(text="\u2796 Delete Player", callback_data="admin:players:delete")],
        [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_teams_keyboard():
    rows = [
        [InlineKeyboardButton(text="\U0001f3cf Add Team", callback_data="admin:teams:add")],
        [InlineKeyboardButton(text="\U0001f464 Assign Owner", callback_data="admin:teams:assign")],
        [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_tournament_keyboard():
    rows = [
        [InlineKeyboardButton(text="\U0001f3c6 Create Tournament", callback_data="admin:tournaments:create")],
        [InlineKeyboardButton(text="\u270f\ufe0f Edit Tournament", callback_data="admin:tournaments:edit")],
        [InlineKeyboardButton(text="\u274c Complete Tournament", callback_data="admin:tournaments:complete")],
        [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_auction_keyboard():
    rows = [
        [InlineKeyboardButton(text="\U0001f534 Start Auction", callback_data="admin:auction:start")],
        [InlineKeyboardButton(text="\u23f8\ufe0f Pause", callback_data="admin:auction:pause"),
         InlineKeyboardButton(text="\u25b6\ufe0f Resume", callback_data="admin:auction:resume")],
        [InlineKeyboardButton(text="\u23f9\ufe0f Stop", callback_data="admin:auction:stop")],
        [InlineKeyboardButton(text="\u2139\ufe0f Status", callback_data="admin:auction:status")],
        [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_manage_keyboard():
    rows = [
        [InlineKeyboardButton(text="\u2795 Add Admin", callback_data="admin:manage:add")],
        [InlineKeyboardButton(text="\u2796 Remove Admin", callback_data="admin:manage:remove")],
        [InlineKeyboardButton(text="\U0001f4cb List Admins", callback_data="admin:manage:list")],
        [InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="home:admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_player_list_keyboard(page, total, page_size):
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05\ufe0f Prev", callback_data=f"admin:players:page:{page-1}"))
    if (page + 1) * page_size < total:
        nav.append(InlineKeyboardButton(text="\u27a1\ufe0f Next", callback_data=f"admin:players:page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="admin:players")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alphabet_keyboard() -> InlineKeyboardMarkup:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rows = [
        [
            InlineKeyboardButton(
                text=letter,
                callback_data=f"players:letter:{letter}",
            )
            for letter in letters[index : index + 6]
        ]
        for index in range(0, len(letters), 6)
    ]
    rows.append([InlineKeyboardButton(text="\u2b05\ufe0f Back", callback_data="home:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def player_list_keyboard(
    letter: str,
    page: int,
    total_players: int,
    *,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    rows = []
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="\u2b05\ufe0f Prev",
                callback_data=f"players:page:{letter}:{page - 1}",
            )
        )
    if (page + 1) * page_size < total_players:
        navigation.append(
            InlineKeyboardButton(
                text="\u27a1\ufe0f Next",
                callback_data=f"players:page:{letter}:{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="\U0001f3e0 Main Menu", callback_data="players:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
                text=f"\U0001f528 +{increment:.2f}",
                callback_data=f"auction:bid_increment:{increment:.2f}",
            ),
            InlineKeyboardButton(
            ),
        ],
        [
            InlineKeyboardButton(
                text="\u270f\ufe0f Custom bid",
                callback_data="auction:custom_bid",
            ),
            InlineKeyboardButton(
                text="\U0001f504 Refresh",
                callback_data="auction:refresh",
            ),
        ],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(text="\u23f8\ufe0f Pause", callback_data="auction:pause"),
                InlineKeyboardButton(text="\u25b6\ufe0f Resume", callback_data="auction:resume"),
                InlineKeyboardButton(text="\u23f9\ufe0f Stop", callback_data="auction:stop"),
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
                text=f"\U0001f7e2 Pending ({pending_count})",
                callback_data=f"auction:cat:pending:{set_number}",
            )
        ])
    if unsold_count > 0:
        rows.append([
            InlineKeyboardButton(
                text=f"\U0001f7e1 Unsold ({unsold_count})",
                callback_data=f"auction:cat:unsold:{set_number}",
            )
        ])
    rows.append([InlineKeyboardButton(text="\u274c Cancel", callback_data="auction:cancel_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timer_keyboard(set_number: int, category: str) -> InlineKeyboardMarkup:
    rows = []
    for secs in [15, 20, 30, 45, 60]:
        rows.append([
            InlineKeyboardButton(
                text=f"\u23f1\ufe0f {secs}s",
                callback_data=f"auction:timer:{set_number}:{category}:{secs}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="\u23f0 Custom",
            callback_data=f"auction:timer:custom:{set_number}:{category}",
        )
    ])
    rows.append([InlineKeyboardButton(text="\u274c Cancel", callback_data="auction:cancel_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
