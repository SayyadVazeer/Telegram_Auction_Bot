"""Render sold and unsold announcement cards as PNG using Pillow."""

from decimal import Decimal
from io import BytesIO

from aiogram import Bot
from PIL import Image, ImageDraw, ImageFont

from app.database.models.player import Player
from app.database.models.team import Team


# -- colours --
_BG_TOP = (7, 26, 42)
_BG_BOT = (21, 61, 86)
_GOLD = (248, 211, 74)
_LIGHT_BLUE = (168, 216, 255)
_PHOTO_BG = (23, 62, 85)
_WHITE = (255, 255, 255)
_GREY = (100, 100, 100)
_BAR_BG = (15, 40, 60)
_BORDER = (60, 120, 160)

# -- layout --
SOLD_W = 700
SOLD_H = 520
UNSOLD_W = 350
UNSOLD_H = 520
PAD = 16
IMG_RADIUS = 14


# -- helpers --
def _gradient_bg(width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(_BG_TOP[0] + (_BG_BOT[0] - _BG_TOP[0]) * ratio)
        g = int(_BG_TOP[1] + (_BG_BOT[1] - _BG_TOP[1]) * ratio)
        b = int(_BG_TOP[2] + (_BG_BOT[2] - _BG_TOP[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


def _rounded_image(source: Image.Image, size: int, radius: int) -> Image.Image:
    resized = source.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (size, size)], radius=radius, fill=255)
    resized.putalpha(mask)
    return resized


def _load_image_bytes(raw: bytes) -> Image.Image:
    return Image.open(BytesIO(raw))


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if bold:
        for path in (
            "arialbd.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "arial.ttf",
        ):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    for path in (
        "arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


async def _download_photo(bot: Bot, file_id: str) -> Image.Image | None:
    try:
        file = await bot.get_file(file_id)
        raw = await bot.download_file(file.file_path)
        return _load_image_bytes(raw.read())
    except Exception:
        return None


# ============================================================
# SOLD CARD  (700 x 500, two halves)
# ============================================================
#   ┌───────────────────────────────────────────────────────┐
#   │ ┌───────────────────────────────────────────────────┐ │
#   │ │  SOLD                              for ₹ 6.70 Cr  │ │
#   │ └───────────────────────────────────────────────────┘ │
#   │  ┌──────────────────────┬──────────────────────────┐  │
#   │  │     Player Photo     │                          │  │
#   │  │                      │      Team Logo           │  │
#   │  │                      │      (fills half)        │  │
#   │  │  Virat Kohli ✈️      │                          │  │
#   │  │  Batsman             │                          │  │
#   │  └──────────────────────┴──────────────────────────┘  │
#   └───────────────────────────────────────────────────────┘
# ============================================================

async def render_sold_card(
    bot: Bot,
    player: Player,
    team: Team,
    final_bid: Decimal,
    owner_username: str | None = None,
) -> bytes:
    player_img = await _download_photo(bot, player.telegram_file_id) if player.telegram_file_id else None
    team_img = await _download_photo(bot, team.logo_file_id) if team.logo_file_id else None

    card = _gradient_bg(SOLD_W, SOLD_H)
    overlay = Image.new("RGBA", (SOLD_W, SOLD_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Outer rounded border
    draw.rounded_rectangle(
        [(10, 10), (SOLD_W - 10, SOLD_H - 10)],
        radius=20, fill=(*_BG_TOP, 240), outline=(*_BORDER, 150), width=2,
    )

    # ── Top bar ──
    bar_x = PAD + 5
    bar_y = PAD
    bar_w = SOLD_W - 2 * PAD - 10
    bar_h = 60
    draw.rounded_rectangle(
        [(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)],
        radius=12, fill=(*_BAR_BG, 230), outline=(*_BORDER, 180), width=2,
    )

    # "SOLD" big
    font_sold = _get_font(80, bold=True)
    draw.text((bar_x + 16, bar_y), "SOLD", fill=(*_WHITE, 255), font=font_sold)

    # "for" + price big
    font_for = _get_font(34, bold=False)
    font_price = _get_font(72, bold=True)
    price_num = f"\u20b9{final_bid:.2f} Cr"
    price_w = _text_width(draw, price_num, font_price)
    for_w = _text_width(draw, "for ", font_for)
    total_w = for_w + price_w
    rx = bar_x + bar_w - total_w - 20
    ry = bar_y + 6
    draw.text((rx, ry + 12), "for ", fill=(*_LIGHT_BLUE, 180), font=font_for)
    draw.text((rx + for_w, ry), price_num, fill=(*_GOLD, 255), font=font_price)

    # ── Two halves ──
    content_y = bar_y + bar_h + 14
    content_h = SOLD_H - content_y - PAD - 10
    half_w = (SOLD_W - 2 * PAD - 10) // 2  # ~327 each
    left_x = PAD + 5
    right_x = left_x + half_w + 10

    # ── Left half: Player photo fills the half ──
    photo_size = min(half_w - 16, content_h - 70, 280)
    photo_x = left_x + (half_w - photo_size) // 2
    photo_y = content_y + 2

    if player_img:
        photo = _rounded_image(player_img, photo_size, IMG_RADIUS)
        overlay.paste(photo, (photo_x, photo_y), photo)
    else:
        draw.rounded_rectangle(
            [(photo_x, photo_y), (photo_x + photo_size, photo_y + photo_size)],
            radius=IMG_RADIUS, fill=(*_PHOTO_BG, 255), outline=(*_BORDER, 100), width=2,
        )

    # Player name + role centered under photo
    overseas = " \u2708\ufe0f" if player.is_overseas else ""
    name_str = player.name + overseas
    font_name = _get_font(52, bold=True)
    font_role = _get_font(36)

    name_w = _text_width(draw, name_str, font_name)
    name_x = left_x + (half_w - name_w) // 2
    name_y = photo_y + photo_size + 6
    draw.text((name_x, name_y), name_str, fill=(*_WHITE, 255), font=font_name)

    role_w = _text_width(draw, player.role, font_role)
    role_x = left_x + (half_w - role_w) // 2
    draw.text((role_x, name_y + 34), player.role, fill=(*_LIGHT_BLUE, 200), font=font_role)

    # ── Right half: Team logo fills the half ──
    logo_size = photo_size
    logo_x = right_x + (half_w - logo_size) // 2
    logo_y = content_y + 2

    if team_img:
        logo = _rounded_image(team_img, logo_size, IMG_RADIUS)
        overlay.paste(logo, (logo_x, logo_y), logo)
    else:
        draw.rounded_rectangle(
            [(logo_x, logo_y), (logo_x + logo_size, logo_y + logo_size)],
            radius=IMG_RADIUS, fill=(*_PHOTO_BG, 255), outline=(*_BORDER, 100), width=2,
        )

    # Team name + code centered under logo
    font_team = _get_font(52, bold=True)
    font_code = _get_font(36)

    team_w = _text_width(draw, team.name, font_team)
    team_x = right_x + (half_w - team_w) // 2
    team_y = logo_y + logo_size + 6
    draw.text((team_x, team_y), team.name, fill=(*_WHITE, 255), font=font_team)

    code_w = _text_width(draw, team.short_code, font_code)
    code_x = right_x + (half_w - code_w) // 2
    draw.text((code_x, team_y + 34), team.short_code, fill=(*_LIGHT_BLUE, 200), font=font_code)

    card.paste(overlay, (0, 0), overlay)
    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ============================================================
# UNSOLD CARD  (350 x 500)
# ============================================================
#   ┌──────────────────────┐
#   │ ┌──────────────────┐ │
#   │ │      Unsold      │ │
#   │ └──────────────────┘ │
#   │  ┌────────────────┐  │
#   │  │  Player Photo  │  │
#   │  │  (fills width) │  │
#   │  └────────────────┘  │
#   │   Virat Kohli ✈️     │
#   │   Batsman            │
#   └──────────────────────┘
# ============================================================

async def render_unsold_card(
    bot: Bot,
    player: Player,
) -> bytes:
    player_img = await _download_photo(bot, player.telegram_file_id) if player.telegram_file_id else None

    card = _gradient_bg(UNSOLD_W, UNSOLD_H)
    overlay = Image.new("RGBA", (UNSOLD_W, UNSOLD_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Outer rounded border
    draw.rounded_rectangle(
        [(8, 8), (UNSOLD_W - 8, UNSOLD_H - 8)],
        radius=18, fill=(*_BG_TOP, 240), outline=(*_BORDER, 150), width=2,
    )

    # Top bar "Unsold"
    bar_x, bar_y = PAD - 2, PAD
    bar_w = UNSOLD_W - 2 * (PAD - 2)
    bar_h = 50
    draw.rounded_rectangle(
        [(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)],
        radius=10, fill=(*_BAR_BG, 230), outline=(*_BORDER, 150), width=2,
    )
    font_label = _get_font(60, bold=True)
    lw = _text_width(draw, "Unsold", font_label)
    draw.text(((UNSOLD_W - lw) // 2, bar_y + 2), "Unsold", fill=(*_GREY, 255), font=font_label)

    # Player photo (fills width)
    content_y = bar_y + bar_h + 10
    photo_size = UNSOLD_W - 2 * (PAD - 2)
    photo_x = (UNSOLD_W - photo_size) // 2
    photo_y = content_y

    if player_img:
        photo = _rounded_image(player_img, photo_size, IMG_RADIUS)
        overlay.paste(photo, (photo_x, photo_y), photo)
    else:
        draw.rounded_rectangle(
            [(photo_x, photo_y), (photo_x + photo_size, photo_y + photo_size)],
            radius=IMG_RADIUS, fill=(*_PHOTO_BG, 255), outline=(*_BORDER, 100), width=2,
        )

    # Player name + role centered
    label_y = photo_y + photo_size + 12
    font_name = _get_font(46, bold=True)
    font_role = _get_font(32)
    overseas = " \u2708\ufe0f" if player.is_overseas else ""
    name_str = player.name + overseas

    name_w = _text_width(draw, name_str, font_name)
    draw.text(((UNSOLD_W - name_w) // 2, label_y), name_str, fill=(*_WHITE, 255), font=font_name)

    role_w = _text_width(draw, player.role, font_role)
    draw.text(((UNSOLD_W - role_w) // 2, label_y + 32), player.role, fill=(*_LIGHT_BLUE, 200), font=font_role)

    card.paste(overlay, (0, 0), overlay)
    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
