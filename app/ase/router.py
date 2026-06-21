import os
from fastapi import APIRouter, HTTPException

from app.ase.memory import create_story, get_story, list_stories, add_episode, delete_story
from app.ase.universe import build_universe
from app.ase.episode_generator import generate_episode
from app.models.ase_schemas import StoryCreateRequest, EpisodeRequest, StorySummary, StoryDetail
from app.core.config import settings
from app.utils.helpers import slugify

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

    # persist updated universe
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
    story = get_story(req.story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    next_number = req.episode_number or len(story["episodes"]) + 1
    episode = generate_episode(story, next_number)

    # optional: render a video for this episode
    video_path = None
    if req.render_video:
        import uuid
        from app.services.script import Script
        from app.services.scenes import split_scenes
        from app.services.image_gen import create_scene_image
        from app.services.voice import generate_voice
        from app.services.video_editor import assemble_video

        job_id = uuid.uuid4().hex[:8]
        job_dir = os.path.join(settings.output_dir, f"ase_{job_id}")

        script = Script(
            hook=episode["hook"],
            body=episode["body"],
            conclusion=episode["cliffhanger"],
        )
        scenes = split_scenes(script)
        image_paths = [
            create_scene_image(s.text, s.index - 1, output_dir=job_dir, is_hook=(s.index == 1))
            for s in scenes
        ]
        voice_path = generate_voice(
            episode["full_script"],
            language=story.get("language", "fr"),
            output_path=os.path.join(job_dir, "voice.mp3"),
        )
        durations = [float(s.duration_hint.rstrip("s")) for s in scenes]
        filename = f"ep{next_number}_{slugify(story['title'])}.mp4"
        video_path = os.path.join(job_dir, filename)
        assemble_video(image_paths, durations, voice_path, video_path)
        episode["video_path"] = video_path
        episode["download_url"] = f"/download/{f'ase_{job_id}'}/{filename}"

    updated_story = add_episode(req.story_id, episode)
    return {
        "episode": episode,
        "world_state": updated_story["world_state"],
        "total_episodes": len(updated_story["episodes"]),
    }
