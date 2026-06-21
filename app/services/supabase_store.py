"""
Supabase persistence for world state via the Supabase REST API.
Uses requests (already in requirements) — no supabase-py dependency needed.

--- SQL setup (run once in Supabase SQL editor) ---

CREATE TABLE universe_storage (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(255) UNIQUE NOT NULL,
    state_json  JSONB NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE TRIGGER trg_universe_storage_updated_at
BEFORE UPDATE ON universe_storage
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

----------------------------------------------------
Then add to Render environment:
  SUPABASE_URL = https://<project-ref>.supabase.co
  SUPABASE_KEY = <anon public key>
"""

import logging
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)

_TABLE = "universe_storage"
_WORLD_KEY = "world_state"
_TIMEOUT = 10


def _headers(*, prefer: str = "") -> dict:
    h = {
        "apikey": settings.supabase_key or "",
        "Authorization": f"Bearer {settings.supabase_key or ''}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def is_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_key)


def load_world() -> dict | None:
    """Fetch world state from Supabase. Returns None if not configured or on error."""
    if not is_configured():
        return None
    try:
        r = requests.get(
            f"{settings.supabase_url}/rest/v1/{_TABLE}",
            headers=_headers(),
            params={"key": f"eq.{_WORLD_KEY}", "select": "state_json"},
            timeout=_TIMEOUT,
        )
        rows = r.json()
        if isinstance(rows, list) and rows:
            return rows[0]["state_json"]
    except Exception as exc:
        logger.warning("Supabase load failed: %s", exc)
    return None


def save_world(state: dict) -> bool:
    """Upsert world state to Supabase. Returns True on success, False on error."""
    if not is_configured():
        return False
    try:
        r = requests.post(
            f"{settings.supabase_url}/rest/v1/{_TABLE}",
            headers=_headers(prefer="resolution=merge-duplicates,return=minimal"),
            json={"key": _WORLD_KEY, "state_json": state},
            timeout=_TIMEOUT,
        )
        return r.status_code in (200, 201, 204)
    except Exception as exc:
        logger.warning("Supabase save failed: %s", exc)
        return False
