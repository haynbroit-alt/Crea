from fastapi import APIRouter, HTTPException

from app.ase.memory import create_story, get_story, list_stories, add_episode, delete_story
from app.ase.universe import build_universe
from app.ase.episode_generator import generate_episode
from app.models.ase_schemas import StoryCreateRequest, EpisodeRequest, StorySummary, StoryDetail

router = APIRouter(prefix="/ase", tags=["ASE — Story Engine"])


@router.get("/stories", response_model=list[StorySummary])
def get_all_stories():
    return list_stories()


@router.post("/stories", response_model=StoryDetail)
def new_story(req: StoryCreateRequest):
    story = create_story(req.title, req.topic, req.language or "fr")
    universe = build_universe(req.topic, req.language or "fr")
    story["universe"] = universe
    story["characters"] = universe["characters"]

    from app.ase.memory import _load, _save
    db = _load()
    db[story["id"]].update({"universe": universe, "characters": universe["characters"]})
    _save(db)
    return story


@router.get("/stories/{story_id}", response_model=StoryDetail)
def get_story_detail(story_id: str):
    story = get_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.delete("/stories/{story_id}")
def remove_story(story_id: str):
    if not delete_story(story_id):
        raise HTTPException(status_code=404, detail="Story not found")
    return {"deleted": story_id}


@router.post("/episodes")
def new_episode(req: EpisodeRequest):
    """
    Synchronous episode generation (text only, no video render).
    For video rendering use POST /ase/episodes/async with render_video=true.
    """
    story = get_story(req.story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    next_number = req.episode_number or len(story["episodes"]) + 1
    episode = generate_episode(story, next_number)
    updated_story = add_episode(req.story_id, episode)

    return {
        "episode": episode,
        "world_state": updated_story["world_state"],
        "total_episodes": len(updated_story["episodes"]),
    }
