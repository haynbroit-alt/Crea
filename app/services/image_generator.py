import os
import random
import urllib.parse
import requests
from PIL import Image, ImageDraw, ImageEnhance

from app.services.image_gen import create_scene_image as _pillow_fallback

_STYLE = "dark watercolor, misty atmosphere, cinematic vertical"
_TIMEOUT = 25


def apply_visual_corruption(image_path: str, corruption_level: float) -> str:
    """
    Apply progressive PIL post-processing based on world corruption level.
    Pure Pillow — no numpy, minimal RAM footprint.

    0.00–0.30  → no-op (Claude's prose carries the mood, WHISPER tier)
    0.31–0.50  → desaturation + horizontal fog scan-lines (MANIFEST tier)
    0.51–1.00  → pixelisation + glitch block shifts + white/black flashes (FRACTURE tier)
    """
    if corruption_level <= 0.3:
        return image_path

    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    draw = ImageDraw.Draw(img)

    if corruption_level <= 0.5:
        # MANIFEST: drain colour + fog scan-lines
        sat_factor = max(0.2, 1.0 - (corruption_level - 0.3) * 2)
        img = ImageEnhance.Color(img).enhance(sat_factor)
        draw = ImageDraw.Draw(img)
        for _ in range(int(10 * corruption_level)):
            y = random.randint(0, height - 1)
            draw.line([(0, y), (width, y)], fill=(20, 20, 25), width=random.randint(1, 3))

    else:
        # FRACTURE: pixelise + glitch bands + flash lines
        pixel_ratio = max(0.05, 1.0 - corruption_level * 0.8)
        small_w = max(1, int(width * pixel_ratio))
        small_h = max(1, int(height * pixel_ratio))
        img = img.resize((small_w, small_h), resample=Image.NEAREST)
        img = img.resize((width, height), resample=Image.NEAREST)
        draw = ImageDraw.Draw(img)

        for _ in range(int(5 * corruption_level)):
            band_h = random.randint(20, 100)
            band_y = random.randint(0, max(0, height - band_h))
            shift = random.randint(-40, 40)
            try:
                band = img.crop((0, band_y, width, band_y + band_h))
                img.paste(band, (shift, band_y))
            except Exception:
                pass  # out-of-bounds crops are silently skipped

        if corruption_level > 0.75:
            draw = ImageDraw.Draw(img)
            for _ in range(int(3 * corruption_level)):
                y = random.randint(0, height - 1)
                colour = random.choice([(0, 0, 0), (255, 255, 255)])
                draw.line([(0, y), (width, y)], fill=colour, width=random.randint(5, 15))

    img.save(image_path, quality=85)
    img.close()
    return image_path


def generate_scene_image(
    description: str,
    index: int,
    output_dir: str,
    is_hook: bool = False,
    corruption_level: float = 0.0,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """
    Fetch image from Pollinations.ai; fall back to local Pillow text image.
    Applies visual corruption in-place if corruption_level > 0.3.
    """
    encoded = urllib.parse.quote(f"{description[:300]}, {_STYLE}")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&model=flux"
    )
    out_path = os.path.join(output_dir, f"scene_{index:03d}.jpg")
    os.makedirs(output_dir, exist_ok=True)

    try:
        r = requests.get(url, timeout=_TIMEOUT)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "image" in ctype:
            with open(out_path, "wb") as f:
                f.write(r.content)
            return apply_visual_corruption(out_path, corruption_level)
    except Exception:
        pass

    path = _pillow_fallback(description, index, output_dir=output_dir, is_hook=is_hook)
    return apply_visual_corruption(path, corruption_level)
