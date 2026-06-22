"""
YouTube Shorts uploader — OAuth2 refresh-token flow, driven entirely by env vars.

Required environment variables (set on Render, never committed):
  YT_CLIENT_ID       OAuth client id      (Google Cloud console)
  YT_CLIENT_SECRET   OAuth client secret
  YT_REFRESH_TOKEN   long-lived refresh token for the channel
Optional:
  YT_PRIVACY         public | unlisted | private   (default: public)

If credentials are absent, upload_short() returns None so the pipeline still
renders and stores the video without ever crashing.
"""
import os

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def is_configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    )


def upload_short(video_path: str, title: str, description: str,
                 tags: list[str] | None = None, category_id: str = "24",
                 privacy: str | None = None) -> dict | None:
    """Upload a video as a Short. Returns {video_id, url} or None if skipped/failed."""
    if not is_configured():
        print("[youtube] credentials absent — skipping upload")
        return None
    if not (video_path and os.path.exists(video_path) and os.path.getsize(video_path) > 0):
        print("[youtube] no video file to upload")
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials(
            token=None,
            refresh_token=os.environ["YT_REFRESH_TOKEN"],
            client_id=os.environ["YT_CLIENT_ID"],
            client_secret=os.environ["YT_CLIENT_SECRET"],
            token_uri=_TOKEN_URI,
            scopes=_SCOPES,
        )
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        body = {
            "snippet": {
                "title": (title or "La Ville qui oublie")[:100],
                "description": (description or "")[:4900],
                "tags": (tags or [])[:30],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": (privacy or os.environ.get("YT_PRIVACY", "public")),
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(video_path, mimetype="video/*",
                                chunksize=1024 * 1024 * 4, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body,
                                          media_body=media)
        response = None
        while response is None:
            _status, response = request.next_chunk()
        vid = response["id"]
        print(f"[youtube] uploaded: https://youtu.be/{vid}")
        return {"video_id": vid, "url": f"https://youtu.be/{vid}"}
    except Exception as exc:
        print(f"[youtube] upload failed: {exc}")
        return None
