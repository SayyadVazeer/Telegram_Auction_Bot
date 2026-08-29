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

# -- layout --
WIDTH = 800
HEIGHT = 500
PAD = 40
IMG_SIZE = 260
IMG_RADIUS = 16


# -- helpers --
def _gradient_bg() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(_BG_TOP[0] + (_BG_BOT[0] - _BG_TOP[0]) * ratio)
        g = int(_BG_TOP[1] + (_BG_BOT[1] - _BG_TOP[1]) * ratio)
        b = int(_BG_TOP[2] + (_BG_BOT[2] - _BG_TOP[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
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


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()


async def _download_photo(bot: Bot, file_id: str) -> Image.Image | None:
    """Download a photo from Telegram by file_id."""
    try:
        file = await bot.get_file(file_id)
        raw = await bot.download_file(file.file_path)
        return _load_image_bytes(raw.read())
    except Exception:
        return None


# -- main renderers --
async def render_sold_card(
    bot: Bot,
    player: Player,
    team: Team,
    final_bid: Decimal,
    owner_username: str | None = None,
) -> bytes:
    """Render a sold-card PNG and return the raw bytes."""

    # 1. download images
    player_img: Image.Image | None = None
    team_img: Image.Image | None = None

    if player.telegram_file_id:
        player_img = await _download_photo(bot, player.telegram_file_id)

    if team.logo_file_id:
        team_img = await _download_photo(bot, team.logo_file_id)

    # 2. build the card
    card = _gradient_bg()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # "SOLD" label
    font_sold = _get_font(36)
    draw.text((PAD, PAD), "SOLD", fill=(*_GOLD, 255), font=font_sold)

    # player photo (left)
    photo_x = PAD
    photo_y = PAD + 60
    if player_img:
        photo = _rounded_image(player_img, IMG_SIZE, IMG_RADIUS)
        overlay.paste(photo, (photo_x, photo_y), photo)
    else:
        draw.rounded_rectangle(
            [(photo_x, photo_y), (photo_x + IMG_SIZE, photo_y + IMG_SIZE)],
            radius=IMG_RADIUS,
            fill=(*_PHOTO_BG, 255),
        )

    # text block (centre)
    text_x = photo_x + IMG_SIZE + 30
    text_y = photo_y + 5

    name_str = player.name
    overseas_tag = " (Overseas)" if player.is_overseas else ""
    font_name = _get_font(48)
    font_detail = _get_font(26)
    font_price = _get_font(52)
    font_owner = _get_font(22)

    draw.text((text_x, text_y), name_str + overseas_tag, fill=(*_WHITE, 255), font=font_name)

    draw.text((text_x, text_y + 55), f"Role: {player.role}", fill=(*_LIGHT_BLUE, 255), font=font_detail)

    team_str = f"{team.name} ({team.short_code})"
    draw.text((text_x, text_y + 90), team_str, fill=(*_LIGHT_BLUE, 255), font=font_detail)

    owner_str = f"Owner: @{owner_username}" if owner_username else ""
    if owner_str:
        draw.text((text_x, text_y + 125), owner_str, fill=(*_LIGHT_BLUE, 255), font=font_owner)

    price_str = f"Rs.{final_bid:.2f} Cr"
    draw.text((text_x, text_y + 170), price_str, fill=(*_GOLD, 255), font=font_price)

    # team logo (right)
    logo_x = WIDTH - PAD - IMG_SIZE
    logo_y = photo_y
    if team_img:
        logo = _rounded_image(team_img, IMG_SIZE, IMG_RADIUS)
        overlay.paste(logo, (logo_x, logo_y), logo)
    else:
        draw.rounded_rectangle(
            [(logo_x, logo_y), (logo_x + IMG_SIZE, logo_y + IMG_SIZE)],
            radius=IMG_RADIUS,
            fill=(*_PHOTO_BG, 255),
        )

    # 3. composite and export
    card.paste(overlay, (0, 0), overlay)

    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def render_unsold_card(
    bot: Bot,
    player: Player,
) -> bytes:
    """Render an unsold-card PNG and return the raw bytes."""

    # 1. download image
    player_img: Image.Image | None = None
    if player.telegram_file_id:
        player_img = await _download_photo(bot, player.telegram_file_id)

    # 2. build the card (darker background for unsold)
    card = Image.new("RGB", (WIDTH, HEIGHT), (30, 30, 35))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # "UNSOLD" label
    font_label = _get_font(36)
    draw.text((PAD, PAD), "UNSOLD", fill=(*_GREY, 255), font=font_label)

    # player photo (center)
    photo_size = 240
    photo_x = (WIDTH - photo_size) // 2
    photo_y = PAD + 70
    if player_img:
        photo = _rounded_image(player_img, photo_size, IMG_RADIUS)
        overlay.paste(photo, (photo_x, photo_y), photo)
    else:
        draw.rounded_rectangle(
            [(photo_x, photo_y), (photo_x + photo_size, photo_y + photo_size)],
            radius=IMG_RADIUS,
            fill=(*_PHOTO_BG, 255),
        )

    # player name
    font_name = _get_font(48)
    name_str = player.name
    overseas_tag = " (Overseas)" if player.is_overseas else ""
    bbox = draw.textbbox((0, 0), name_str + overseas_tag, font=font_name)
    tw = bbox[2] - bbox[0]
    name_y = photo_y + photo_size + 20
    draw.text(((WIDTH - tw) // 2, name_y), name_str + overseas_tag, fill=(*_WHITE, 255), font=font_name)

    # role
    font_role = _get_font(28)
    role_str = player.role
    bbox = draw.textbbox((0, 0), role_str, font=font_role)
    rw = bbox[2] - bbox[0]
    draw.text(((WIDTH - rw) // 2, name_y + 55), role_str, fill=(*_GREY, 255), font=font_role)

    # "No bids received"
    font_sub = _get_font(22)
    sub_str = "No bids received"
    bbox = draw.textbbox((0, 0), sub_str, font=font_sub)
    sw = bbox[2] - bbox[0]
    draw.text(((WIDTH - sw) // 2, name_y + 100), sub_str, fill=(150, 150, 150), font=font_sub)

    # 3. composite and export
    card.paste(overlay, (0, 0), overlay)

    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
