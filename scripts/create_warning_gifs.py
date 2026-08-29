"""Generate auction warning GIFs.

once.gif  - 'Going once' with hammer symbol (shown at 10s)
twice.gif - 'Going twice' with hammer symbol (shown at 5s)
"""

from PIL import Image, ImageDraw, ImageFont

SIZE = 512


def _get_font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except OSError:
            return ImageFont.load_default()


def _draw_frame(text: str, sub: str, bg_color: tuple, accent: tuple, symbol: str) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), bg_color)
    draw = ImageDraw.Draw(img)

    # Draw gavel/hammer symbol (simple rectangle shapes)
    cx, cy = SIZE // 2, SIZE // 2 - 50

    # Hammer head (rectangle)
    head_w, head_h = 100, 60
    draw.rounded_rectangle(
        [(cx - head_w // 2, cy - head_h // 2),
         (cx + head_w // 2, cy + head_h // 2)],
        radius=10, fill=accent,
    )

    # Handle (vertical line)
    handle_w = 12
    handle_h = 120
    draw.rounded_rectangle(
        [(cx - handle_w // 2, cy + head_h // 2 - 5),
         (cx + handle_w // 2, cy + head_h // 2 + handle_h)],
        radius=4, fill=(180, 140, 80),
    )

    # Sound lines (motion effect)
    for offset in [-80, 80]:
        x = cx + offset
        draw.line([(x, cy - 40), (x + (20 if offset > 0 else -20), cy - 70)],
                  fill=(*accent, 200), width=4)

    # Main text
    font_main = _get_font(64)
    bbox = draw.textbbox((0, 0), text, font=font_main)
    tw = bbox[2] - bbox[0]
    draw.text((SIZE // 2 - tw // 2, SIZE - 160), text, fill=accent, font=font_main)

    # Sub text
    if sub:
        font_sub = _get_font(36)
        bbox = draw.textbbox((0, 0), sub, font=font_sub)
        sw = bbox[2] - bbox[0]
        draw.text((SIZE // 2 - sw // 2, SIZE - 80), sub, fill=(180, 180, 180), font=font_sub)

    return img


# once.gif - Going once (single pulse)
once_frames = [
    _draw_frame("GOING ONCE", "", (25, 25, 30), (255, 180, 50), "hammer"),
    _draw_frame("GOING ONCE", "", (40, 35, 20), (220, 160, 40), "hammer"),
    _draw_frame("GOING ONCE", "", (25, 25, 30), (255, 180, 50), "hammer"),
]
once_frames[0].save(
    "data/once.gif",
    save_all=True,
    append_images=once_frames[1:],
    duration=[500, 400, 500],
    loop=0,
)

# twice.gif - Going twice (double pulse)
twice_frames = [
    _draw_frame("GOING TWICE", "Last chance!", (25, 25, 30), (255, 120, 50), "hammer"),
    _draw_frame("GOING TWICE", "Last chance!", (40, 25, 15), (220, 100, 40), "hammer"),
    _draw_frame("GOING TWICE", "Last chance!", (25, 25, 30), (255, 120, 50), "hammer"),
    _draw_frame("GOING TWICE", "Last chance!", (40, 25, 15), (220, 100, 40), "hammer"),
    _draw_frame("GOING TWICE", "Last chance!", (25, 25, 30), (255, 120, 50), "hammer"),
]
twice_frames[0].save(
    "data/twice.gif",
    save_all=True,
    append_images=twice_frames[1:],
    duration=[400, 300, 400, 300, 400],
    loop=0,
)

print("Created data/once.gif and data/twice.gif")
