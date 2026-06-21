import os
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.jobs.store import update_job, JobStatus
from app.utils.helpers import slugify


def render_video_task(job_id: str, params: dict) -> None:
    from app.services.script import generate_script
    from app.services.scenes import split_scenes
    from app.services.image_gen import create_scene_image
    from app.services.voice import generate_voice
    from app.services.video_editor import assemble_video

    update_job(job_id, status=JobStatus.PROCESSING, started_at=datetime.now(timezone.utc).isoformat())
    try:
        topic = params["topic"]
        language = params.get("language", "fr")
        style = params.get("style", "viral")
        render_id = uuid.uuid4().hex[:8]
        job_dir = os.path.join(settings.output_dir, render_id)

        script = generate_script(topic, language=language, style=style)
        scenes = split_scenes(script)

        image_paths = [
            create_scene_image(s.text, s.index - 1, output_dir=job_dir, is_hook=(s.index == 1))
            for s in scenes
        ]
        full_text = " ".join([script.hook] + script.body + [script.conclusion])
        voice_path = generate_voice(
            full_text, language=language,
            output_path=os.path.join(job_dir, "voice.mp3"),
        )
        durations = [float(s.duration_hint.rstrip("s")) for s in scenes]
        filename = f"{slugify(topic)}.mp4"
        output_path = os.path.join(job_dir, filename)
        assemble_video(image_paths, durations, voice_path, output_path)

        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            result={
                "render_id": render_id,
                "video_path": output_path,
                "download_url": f"/download/{render_id}/{filename}",
                "scene_count": len(scenes),
            },
        )
    except Exception as exc:
        update_job(
            job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )


def ase_episode_task(job_id: str, params: dict) -> None:
    from app.ase.memory import get_story, add_episode
    from app.ase.episode_generator import generate_episode
    from app.services.script import Script
    from app.services.scenes import split_scenes
    from app.services.image_gen import create_scene_image
    from app.services.voice import generate_voice
    from app.services.video_editor import assemble_video

    update_job(job_id, status=JobStatus.PROCESSING, started_at=datetime.now(timezone.utc).isoformat())
    try:
        story_id = params["story_id"]
        episode_number = params.get("episode_number")
        render_video = params.get("render_video", False)

        story = get_story(story_id)
        if not story:
            raise ValueError(f"Story {story_id!r} not found")

        next_number = episode_number or len(story["episodes"]) + 1
        episode = generate_episode(story, next_number)

        if render_video:
            render_id = uuid.uuid4().hex[:8]
            job_dir = os.path.join(settings.output_dir, f"ase_{render_id}")
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
            output_path = os.path.join(job_dir, filename)
            assemble_video(image_paths, durations, voice_path, output_path)
            episode["video_path"] = output_path
            episode["download_url"] = f"/download/ase_{render_id}/{filename}"

        updated_story = add_episode(story_id, episode)
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            result={
                "episode": episode,
                "world_state": updated_story["world_state"],
                "total_episodes": len(updated_story["episodes"]),
            },
        )
    except Exception as exc:
        update_job(
            job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
