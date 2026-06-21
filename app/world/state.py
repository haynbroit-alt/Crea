import json
import os
import threading
from datetime import datetime, timezone

from app.world.catalog import MEMORIES, get_memory, next_dilemma

_lock = threading.Lock()
_DB = os.environ.get("WORLD_DB_PATH", "data/world.json")


def _load() -> dict:
    from app.services.supabase_store import load_world as _sb_load, is_configured as _sb_ok
    if _sb_ok():
        try:
            remote = _sb_load()
            if remote:
                # Refresh local cache so restarts are fast
                os.makedirs(os.path.dirname(_DB) or ".", exist_ok=True)
                with open(_DB, "w", encoding="utf-8") as f:
                    json.dump(remote, f, indent=2, ensure_ascii=False)
                return remote
        except Exception:
            pass
    if os.path.exists(_DB):
        with open(_DB, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(world: dict) -> None:
    os.makedirs(os.path.dirname(_DB) or ".", exist_ok=True)
    with open(_DB, "w", encoding="utf-8") as f:
        json.dump(world, f, indent=2, ensure_ascii=False)
    from app.services.supabase_store import save_world as _sb_save, is_configured as _sb_ok
    if _sb_ok():
        try:
            _sb_save(world)
        except Exception:
            pass


def get_world() -> dict:
    with _lock:
        return _load()


def save_world(world: dict) -> None:
    with _lock:
        _save(world)


def init_world(reset: bool = False) -> dict:
    """Bootstrap Day 1: strawberry taste already discovered missing."""
    with _lock:
        existing = _load()
        if existing and not reset:
            return existing

        world = {
            "world_name": "La Ville qui oublie",
            "day": 1,
            "collective_sanity": 95,   # already -5 from strawberry_taste
            "infrastructure_level": 100,
            "wonder_level": 92,        # already -8
            "alive_memories": [m for m in MEMORIES if m != "strawberry_taste"],
            "lost_memories": ["strawberry_taste"],
            "protected_memories": [],
            "current_dilemma": {
                "threat": (
                    "La Brume revient cette nuit. "
                    "Le Conseil a découvert qu'il peut en protéger un seul. "
                    "L'autre disparaîtra à l'aube."
                ),
                "option_A": {
                    "protect": "strawberry_taste",
                    "sacrifice": "child_laughter",
                    "label_protect": get_memory("strawberry_taste")["name"],
                    "label_sacrifice": get_memory("child_laughter")["name"],
                },
                "option_B": {
                    "protect": "child_laughter",
                    "sacrifice": "strawberry_taste",
                    "label_protect": get_memory("child_laughter")["name"],
                    "label_sacrifice": get_memory("strawberry_taste")["name"],
                },
            },
            "vote_counts": {"A": 0, "B": 0},
            "voting_open": True,
            "episodes": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(world)
        return world


def cast_vote(option: str) -> dict:
    if option not in ("A", "B"):
        raise ValueError("option must be 'A' or 'B'")
    with _lock:
        world = _load()
        if not world:
            raise RuntimeError("World not initialised — call POST /world/init first")
        if not world.get("voting_open"):
            raise RuntimeError("Voting is closed for today")
        world["vote_counts"][option] += 1
        _save(world)
        return {"votes": world["vote_counts"], "day": world["day"]}
