"""
YouTube Shorts uploader + one-click OAuth, driven by env vars.

Easiest path for the operator: open /youtube/connect in the dashboard, sign in
to Google once, and the refresh token is captured and persisted automatically
(Supabase if configured, else a local file). No Playground, no script, no manual
token copying.

Environment variables:
  YT_CLIENT_ID       OAuth *Web* client id      (Google Cloud console)
  YT_CLIENT_SECRET   OAuth *Web* client secret
  YT_REFRESH_TOKEN   (optional) overrides the stored token
  YT_PRIVACY         public | unlisted | private   (default: public)

If no credentials/token are available, upload_short() returns None so the
pipeline still renders and stores the video without ever crashing.
"""
import json
import os

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
_STORE_KEY = "youtube_credentials"
_TOKEN_FILE = "data/youtube.json"


# ── credentials & token storage ──────────────────────────────────────────────

def client_ready() -> bool:
    return bool(os.environ.get("YT_CLIENT_ID") and os.environ.get("YT_CLIENT_SECRET"))


def get_refresh_token() -> str | None:
    if os.environ.get("YT_REFRESH_TOKEN"):
        return os.environ["YT_REFRESH_TOKEN"]
    try:
        from app.services.supabase_store import load_value, is_configured
        if is_configured():
            data = load_value(_STORE_KEY) or {}
            if data.get("refresh_token"):
                return data["refresh_token"]
    except Exception:
        pass
    try:
        with open(_TOKEN_FILE, encoding="utf-8") as f:
            return (json.load(f) or {}).get("refresh_token")
    except Exception:
        return None


def save_refresh_token(token: str) -> None:
    saved = False
    try:
        from app.services.supabase_store import save_value, is_configured
        if is_configured():
            saved = save_value(_STORE_KEY, {"refresh_token": token})
    except Exception:
        pass
    try:                                  # always keep a local copy too
        os.makedirs(os.path.dirname(_TOKEN_FILE) or ".", exist_ok=True)
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"refresh_token": token}, f)
    except Exception:
        pass
    print(f"[youtube] refresh token saved (supabase={saved})")


def is_configured() -> bool:
    return client_ready() and bool(get_refresh_token())


# ── one-click OAuth (manual flow, no oauthlib dependency) ─────────────────────

def auth_url(redirect_uri: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": os.environ.get("YT_CLIENT_ID", ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",
        "prompt": "consent",            # force a refresh_token every time
        "include_granted_scopes": "true",
    }
    return f"{_AUTH_URI}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> tuple[bool, str]:
    """Exchange an auth code for tokens; persist the refresh token."""
    import requests
    try:
        r = requests.post(_TOKEN_URI, timeout=20, data={
            "code": code,
            "client_id": os.environ.get("YT_CLIENT_ID", ""),
            "client_secret": os.environ.get("YT_CLIENT_SECRET", ""),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        data = r.json()
        if r.status_code != 200:
            return False, data.get("error_description") or data.get("error") or r.text[:200]
        token = data.get("refresh_token")
        if not token:
            return False, ("Aucun refresh_token renvoyé. Révoque l'accès de l'app dans "
                           "ton compte Google puis reconnecte-toi (prompt=consent).")
        save_refresh_token(token)
        return True, token
    except Exception as exc:
        return False, str(exc)


# ── upload ───────────────────────────────────────────────────────────────────

def upload_short(video_path: str, title: str, description: str,
                 tags: list[str] | None = None, category_id: str = "24",
                 privacy: str | None = None) -> dict | None:
    """Upload a video as a Short. Returns {video_id, url} or None if skipped/failed."""
    refresh_token = get_refresh_token()
    if not (client_ready() and refresh_token):
        print("[youtube] not connected — skipping upload")
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
            refresh_token=refresh_token,
            client_id=os.environ["YT_CLIENT_ID"],
            client_secret=os.environ["YT_CLIENT_SECRET"],
            token_uri=_TOKEN_URI,
            scopes=[_SCOPE],
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
