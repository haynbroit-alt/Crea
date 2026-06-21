import json
import os
import uuid
from datetime import datetime, timezone

_DB_PATH = os.environ.get("ASE_DB_PATH", "data/stories.json")


def _load() -> dict:
    if not os.path.exists(_DB_PATH):
        return {}
    with open(_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(db: dict) -> None:
    os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
    with open(_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def create_story(title: str, topic: str, language: str = "fr") -> dict:
    db = _load()
    story_id = uuid.uuid4().hex[:10]
    story = {
        "id": story_id,
        "title": title,
        "topic": topic,
        "language": language,
        "universe": {},
        "characters": [],
        "episodes": [],
        "world_state": {"tension": 0, "mystery_level": 1},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db[story_id] = story
    _save(db)
    return story


def get_story(story_id: str) -> dict | None:
    return _load().get(story_id)


def list_stories() -> list[dict]:
    db = _load()
    return [
        {"id": s["id"], "title": s["title"], "topic": s["topic"],
         "episode_count": len(s["episodes"]), "created_at": s["created_at"]}
        for s in db.values()
    ]


def add_episode(story_id: str, episode: dict) -> dict:
    db = _load()
    if story_id not in db:
        raise KeyError(f"Story {story_id!r} not found")
    db[story_id]["episodes"].append(episode)
    # evolve world state
    db[story_id]["world_state"]["tension"] = min(10, db[story_id]["world_state"]["tension"] + 1)
    db[story_id]["world_state"]["mystery_level"] = min(5, len(db[story_id]["episodes"]) // 2 + 1)
    _save(db)
    return db[story_id]


def delete_story(story_id: str) -> bool:
    db = _load()
    if story_id not in db:
        return False
    del db[story_id]
    _save(db)
    return True
