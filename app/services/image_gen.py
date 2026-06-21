from PIL import Image, ImageDraw, ImageFont
import os
import textwrap

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

_ACCENT_COLORS = [
    (255, 214, 0),    # gold
    (0, 200, 255),    # cyan
    (255, 100, 100),  # coral
    (100, 255, 160),  # mint
]

W, H = 1080, 1920


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(text: str, width: int = 22) -> str:
    return textwrap.fill(text, width=width)


def create_scene_image(
    text: str,
    index: int,
    output_dir: str = "output",
    is_hook: bool = False,
) -> str:
    bg_color = (10, 10, 10)
    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # subtle gradient bar at top
    accent = _ACCENT_COLORS[index % len(_ACCENT_COLORS)]
    draw.rectangle([0, 0, W, 12], fill=accent)
    draw.rectangle([0, H - 12, W, H], fill=accent)

    font_size = 88 if is_hook else 72
    font = _get_font(font_size)
    small_font = _get_font(40)

    wrapped = _wrap(text, width=20 if is_hook else 24)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (W - text_w) // 2
    y = (H - text_h) // 2

    # drop shadow
    draw.multiline_text((x + 5, y + 5), wrapped, font=font, fill=(0, 0, 0), align="center")
    # main text
    text_color = accent if is_hook else (255, 255, 255)
    draw.multiline_text((x, y), wrapped, font=font, fill=text_color, align="center")

    # scene counter
    counter = f"{index + 1}"
    draw.text((W - 80, H - 90), counter, font=small_font, fill=(80, 80, 80))

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"scene_{index:03d}.png")
    img.save(path, "PNG")
    return path
