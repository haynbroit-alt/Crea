import json
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


def world_episode_task(job_id: str, params: dict) -> None:
    """
    Full pipeline for a world episode:
    advance state → narrate (Claude) → Pollinations images → voice → video + music ducking → Discord notify.
    """
    from app.world.engine import advance_day
    from app.world.state import get_world
    from app.world.music import generate_music
    from app.services.image_generator import generate_scene_image
    from app.services.voice import generate_voice
    from app.services.video_editor import assemble_video
    from app.services.notifier import notify_discord

    update_job(job_id, status=JobStatus.PROCESSING, started_at=datetime.now(timezone.utc).isoformat())
    try:
        episode = advance_day()
        world = get_world()
        day = episode["day"]
        render_id = uuid.uuid4().hex[:8]
        job_dir = os.path.join(settings.output_dir, f"world_ep{day}_{render_id}")

        # Music WAV (procedural, matches world mood)
        music_path = os.path.join(settings.output_dir, "world", f"day_{day}_music.wav")
        os.makedirs(os.path.dirname(music_path), exist_ok=True)
        generate_music(world, music_path)

        # Images — one per act (Pollinations → Pillow fallback, corruption applied in-place)
        acts = episode.get("acts", {})
        corruption = world.get("system_corruption_level", 0.0)
        scene_specs = [
            (acts.get("act1", {}).get("text", ""), True),
            (acts.get("act2", {}).get("text", ""), False),
            (acts.get("act3", {}).get("text", ""), False),
        ]
        image_paths = [
            generate_scene_image(
                text[:300], i, output_dir=job_dir,
                is_hook=is_hook, corruption_level=corruption,
            )
            for i, (text, is_hook) in enumerate(scene_specs)
            if text
        ]

        # Voice — full episode narration
        full_text = episode.get("full_script", f"Jour {day}.")
        voice_path = generate_voice(
            full_text,
            language="fr",
            output_path=os.path.join(job_dir, "voice.mp3"),
        )

        # Video assembly with music ducking (12% volume under voice)
        durations = [45.0, 60.0, 30.0][: len(image_paths)]
        filename = f"world_ep{day}.mp4"
        output_path = os.path.join(job_dir, filename)
        assemble_video(image_paths, durations, voice_path, output_path, music_path=music_path)

        # Discord notification (no-op if DISCORD_WEBHOOK_URL not set)
        call_to_vote = acts.get("act4", {}).get("text", f"Épisode {day} en ligne.")
        notify_discord(day, output_path, call_to_vote)

        # Persist latest episode URL for /godmode video player
        media_url = f"/media/world_ep{day}_{render_id}/{filename}"
        _last_ep = {"day": day, "url": media_url, "render_id": render_id}
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/last_episode.json", "w", encoding="utf-8") as _f:
                json.dump(_last_ep, _f)
        except Exception:
            pass

        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            result={
                "day": day,
                "render_id": render_id,
                "media_url": media_url,
                "download_url": f"/download/world_ep{day}_{render_id}/{filename}",
                "episode": episode,
            },
        )
    except Exception as exc:
        update_job(
            job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )


def _publish_meta(episode: dict, branding: dict) -> tuple[str, str, list[str]]:
    """Build SEO-optimised YouTube title, description and tags for a Short."""
    from app.world.catalog import get_memory

    day = episode.get("day", "?")
    lost_id = episode.get("lost")
    lost_name = get_memory(lost_id).get("name", lost_id) if lost_id else "un souvenir"
    acts = episode.get("acts", {})
    act1 = acts.get("act1", {}).get("text", "").strip()
    act4 = acts.get("act4", {}).get("text", "").strip()

    title = f"Jour {day} : {lost_name} a disparu 🌫️ #Shorts"

    parts = [act1, "", "🗳️ " + act4 if act4 else "", "", branding.get("subscribe", "")]
    if branding.get("link"):
        parts.append(branding["link"])
    if branding.get("sponsor"):
        parts.append(f"Avec le soutien de : {branding['sponsor']}")
    parts += ["", "#Shorts #fiction #IA #cyberpunk #histoire #LaVilleQuiOublie #storytelling"]
    description = "\n".join(p for p in parts if p is not None)

    tags = ["La Ville qui oublie", "fiction interactive", "IA", "cyberpunk",
            "histoire", "Shorts", "storytelling", "brume", str(lost_name)]
    return title[:100], description, tags


def world_publish_task(job_id: str, params: dict) -> None:
    """
    Free, low-RAM Shorts pipeline:
    advance → Claude narration → Pollinations images → gTTS voice →
    procedural music → ffmpeg branded Short (intro/outro/watermark/sponsor) →
    YouTube upload (graceful) → Discord notify.
    """
    from app.world.engine import advance_day
    from app.world.state import get_world
    from app.world.music import generate_music
    from app.services.image_generator import generate_scene_image
    from app.services.voice import generate_voice
    from app.services.ffmpeg_render import render_short
    from app.services.youtube import upload_short
    from app.services.branding import branding_config
    from app.services.notifier import notify_discord

    update_job(job_id, status=JobStatus.PROCESSING, started_at=datetime.now(timezone.utc).isoformat())
    try:
        advance = params.get("advance", True)
        existing = get_world()
        if advance or not (existing and existing.get("episodes")):
            episode = advance_day()
        else:
            episode = existing["episodes"][-1]

        world = get_world()
        day = episode["day"]
        render_id = uuid.uuid4().hex[:8]
        job_dir = os.path.join(settings.output_dir, f"world_pub{day}_{render_id}")
        os.makedirs(job_dir, exist_ok=True)
        branding = branding_config()

        # Procedural music (matches world mood)
        music_path = os.path.join(job_dir, "music.wav")
        try:
            generate_music(world, music_path)
        except Exception:
            music_path = None

        # One image per act (Pollinations → Pillow fallback, corruption applied)
        acts = episode.get("acts", {})
        corruption = world.get("system_corruption_level", 0.0)
        specs = [
            (acts.get("act1", {}).get("text", ""), True),
            (acts.get("act2", {}).get("text", ""), False),
            (acts.get("act3", {}).get("text", ""), False),
        ]
        image_paths = [
            generate_scene_image(text[:300], i, output_dir=job_dir,
                                 is_hook=is_hook, corruption_level=corruption)
            for i, (text, is_hook) in enumerate(specs) if text
        ]

        # Concise narration (consequences + call to vote) for a Short
        act1 = acts.get("act1", {}).get("text", "").strip()
        act4 = acts.get("act4", {}).get("text", "").strip()
        narration = " ".join(x for x in [act1, act4] if x)[:600] or f"Jour {day}."
        voice_path = None
        try:
            voice_path = generate_voice(narration, language="fr",
                                        output_path=os.path.join(job_dir, "voice.mp3"))
        except Exception:
            voice_path = None

        # Branded vertical Short via ffmpeg (low RAM)
        n = len(image_paths) or 1
        durations = [12.0] * n
        out_name = f"world_short_{day}.mp4"
        output_path = os.path.join(job_dir, out_name)
        video = render_short(
            image_paths, durations, output_path,
            voice_path=voice_path, music_path=music_path,
            title=branding["intro_title"], cta=branding["cta"],
            watermark=branding["watermark"], sponsor=branding["sponsor"],
            work_dir=job_dir,
        )

        # SEO metadata + YouTube upload (no-op if creds absent)
        title, description, tags = _publish_meta(episode, branding)
        youtube = upload_short(video, title, description, tags) if video else None

        # Discord notification (no-op if webhook absent)
        try:
            notify_discord(day, video or "", act4 or f"Épisode {day} en ligne.")
        except Exception:
            pass

        media_url = f"/media/world_pub{day}_{render_id}/{out_name}" if video else None
        last = {"day": day, "media_url": media_url, "youtube": youtube, "title": title}
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/last_publish.json", "w", encoding="utf-8") as f:
                json.dump(last, f, ensure_ascii=False)
        except Exception:
            pass

        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            result={
                "day": day,
                "rendered": bool(video),
                "media_url": media_url,
                "download_url": f"/download/world_pub{day}_{render_id}/{out_name}" if video else None,
                "youtube": youtube,
                "title": title,
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
