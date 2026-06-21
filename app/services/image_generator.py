import os
import urllib.parse
import requests

from app.services.image_gen import create_scene_image as _pillow_fallback

_STYLE = "dark watercolor, misty atmosphere, cinematic vertical"
_TIMEOUT = 25


def generate_scene_image(
    description: str,
    index: int,
    output_dir: str,
    is_hook: bool = False,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """
    Fetch image from Pollinations.ai; fall back to local Pillow text image.
    Drop-in replacement for create_scene_image().
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
            return out_path
    except Exception:
        pass

    return _pillow_fallback(description, index, output_dir=output_dir, is_hook=is_hook)
