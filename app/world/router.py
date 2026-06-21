import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from app.world.state import get_world, cast_vote, init_world
from app.world.engine import advance_day
from app.world.narrator import generate_script
from app.world.catalog import MEMORIES
from app.world.music import generate_music, derive_music_params
from app.core.config import settings

router = APIRouter(prefix="/world", tags=["World Engine — La Ville qui oublie"])


class VoteRequest(BaseModel):
    option: Literal["A", "B"]


@router.post("/init")
def initialise_world(reset: bool = False):
    """Bootstrap the world. Idempotent unless reset=true."""
    return init_world(reset=reset)


@router.get("/state")
def world_state():
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised — POST /world/init first")
    return world


@router.get("/episode")
def current_episode():
    """Generate (but don't advance) the script for today."""
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised")
    return generate_script(world)


@router.get("/episodes")
def episode_history():
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised")
    return {
        "day": world["day"],
        "total_episodes": len(world["episodes"]),
        "episodes": world["episodes"],
    }


@router.get("/episodes/{day}")
def episode_by_day(day: int):
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised")
    for ep in world["episodes"]:
        if ep["day"] == day:
            return ep
    raise HTTPException(status_code=404, detail=f"No episode found for day {day}")


@router.post("/vote")
def vote(req: VoteRequest):
    try:
        return cast_vote(req.option)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/advance")
def advance(render: bool = False, background_tasks=None):
    """
    Close voting, apply the winning choice, generate today's episode,
    and prepare tomorrow's dilemma. Call once per day (via cron or manually).

    Pass ?render=true to also kick off a background video render job
    (Pollinations images + music ducking + Discord notification).
    """
    from fastapi import BackgroundTasks as _BT
    from app.jobs.store import create_job
    from app.jobs.worker import submit
    from app.jobs.tasks import world_episode_task

    if render:
        job = create_job("world_episode", {})
        submit(world_episode_task, job["id"], {})
        return {
            "status": "accepted",
            "job_id": job["id"],
            "status_url": f"/jobs/{job['id']}/status",
            "message": "Le monde avance. La forge démarre en arrière-plan.",
        }

    try:
        return advance_day()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/memories")
def list_memories():
    world = get_world()
    lost = set(world.get("lost_memories", [])) if world else set()
    protected = set(world.get("protected_memories", [])) if world else set()
    return [
        {
            "id": mid,
            "name": mem["name"],
            "tier": mem["tier"],
            "status": "lost" if mid in lost else ("protected" if mid in protected else "alive"),
        }
        for mid, mem in MEMORIES.items()
    ]


@router.get("/music")
def current_music_params():
    """Music parameters derived from current world state (no file generated)."""
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised")
    return derive_music_params(world)


@router.post("/music/render")
def render_music():
    """Generate a WAV file for the current world state. Returns download path."""
    from fastapi.responses import FileResponse
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised")
    out_path = os.path.join(settings.output_dir, "world", f"day_{world['day']}_music.wav")
    params = generate_music(world, out_path)
    return {**params, "download_url": f"/download/world/day_{world['day']}_music.wav"}


@router.get("/music/{day}")
def music_by_day(day: int):
    """Replay music params for a past episode (from stored episode data)."""
    world = get_world()
    if not world:
        raise HTTPException(status_code=404, detail="World not initialised")
    for ep in world["episodes"]:
        if ep["day"] == day:
            return ep.get("music_params", derive_music_params(world))
    raise HTTPException(status_code=404, detail=f"No episode for day {day}")


@router.delete("/reset")
def reset_world():
    """Hard reset — Day 1, fresh state."""
    return init_world(reset=True)
