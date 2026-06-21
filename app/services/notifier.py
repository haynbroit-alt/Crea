import os
import requests


def notify_discord(episode_num: int, video_path: str | None, description: str) -> bool:
    """
    Send episode text + optional video file to a Discord webhook.
    Silent no-op if DISCORD_WEBHOOK_URL is not set.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False
    try:
        requests.post(
            webhook_url,
            json={"content": f"🌫️ **Épisode {episode_num} PRÊT**\n\n{description}"},
            timeout=10,
        )
        if video_path and os.path.exists(video_path):
            size = os.path.getsize(video_path)
            if 0 < size < 8 * 1024 * 1024:  # Discord free tier: 8 MB cap
                with open(video_path, "rb") as f:
                    requests.post(
                        webhook_url,
                        files={"file": ("episode.mp4", f, "video/mp4")},
                        timeout=60,
                    )
        return True
    except Exception as exc:
        print(f"Discord notification failed: {exc}")
        return False
