"""
Branding & advertising configuration for the YouTube Shorts pipeline.

Everything is driven by environment variables so nothing sensitive or
deployment-specific lives in the repo. Sensible on-theme defaults are provided
so the pipeline produces a polished, branded video even with zero configuration.
"""
import os


def _env(key: str, default: str = "") -> str:
    # allow literal "\n" in env values to become real line breaks (for drawtext)
    return os.environ.get(key, default).replace("\\n", "\n")


def branding_config() -> dict:
    channel = _env("BRAND_CHANNEL", "La Ville qui oublie")
    return {
        # animated intro card
        "intro_title": _env("BRAND_INTRO", "LA VILLE\nQUI OUBLIE"),
        # animated outro / call-to-action card
        "cta": _env(
            "BRAND_CTA",
            "VOTE A ou B\nen commentaire\n\nUn souvenir disparaît à l'aube",
        ),
        # discreet watermark in the corner across the whole video
        "watermark": _env("BRAND_WATERMARK", channel),
        # optional sponsor banner along the bottom — empty string disables it
        "sponsor": _env("BRAND_SPONSOR", ""),
        # used in the YouTube description
        "channel": channel,
        "subscribe": _env(
            "BRAND_SUBSCRIBE",
            "Abonne-toi pour suivre la chute de la ville, un souvenir à la fois.",
        ),
        "link": _env("BRAND_LINK", ""),
    }
