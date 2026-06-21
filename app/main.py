import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import settings
from app.models.schemas import VideoRequest, VideoPlan, RenderResult
from app.services.script import generate_script
from app.services.scenes import split_scenes
from app.services.seo import generate_seo
from app.services.video_plan import build_video_plan
from app.services.image_gen import create_scene_image
from app.services.voice import generate_voice
from app.services.video_editor import assemble_video
from app.utils.helpers import slugify

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for AI-powered short-form video generation",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "status": "running",
        "app": settings.app_name,
        "version": settings.app_version,
        "message": "AI Video Agent ready 🚀",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=VideoPlan)
def generate_video(request: VideoRequest):
    if not request.topic.strip():
        raise HTTPException(status_code=422, detail="topic cannot be empty")

    topic = request.topic.strip()
    language = request.language or "fr"
    style = request.style or "viral"

    script = generate_script(topic, language=language, style=style)
    scenes = split_scenes(script)
    seo = generate_seo(topic, language=language)
    plan = build_video_plan(topic, language, style, script, scenes, seo)

    return plan


@app.post("/render", response_model=RenderResult)
def render_video(request: VideoRequest):
    """
    Full pipeline: script → scene images → voice → MP4 assembly.
    Returns a download URL for the finished video.
    Note: rendering takes 30–120s depending on server load.
    """
    if not request.topic.strip():
        raise HTTPException(status_code=422, detail="topic cannot be empty")

    topic = request.topic.strip()
    language = request.language or "fr"
    style = request.style or "viral"
    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(settings.output_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # 1. Script + scenes
    script = generate_script(topic, language=language, style=style)
    scenes = split_scenes(script)

    # 2. Scene images
    image_paths = []
    for scene in scenes:
        path = create_scene_image(
            scene.text,
            scene.index - 1,
            output_dir=job_dir,
            is_hook=(scene.index == 1),
        )
        image_paths.append(path)

    # 3. Voice
    full_text = " ".join([script.hook] + script.body + [script.conclusion])
    voice_path = generate_voice(full_text, language=language, output_path=os.path.join(job_dir, "voice.mp3"))

    # 4. Durations from scene hints
    durations = []
    for scene in scenes:
        try:
            durations.append(float(scene.duration_hint.rstrip("s")))
        except ValueError:
            durations.append(4.0)

    # 5. Assemble
    output_path = os.path.join(job_dir, f"{slugify(topic)}.mp4")
    assemble_video(image_paths, durations, voice_path, output_path)

    return RenderResult(
        job_id=job_id,
        topic=topic,
        video_path=output_path,
        download_url=f"/download/{job_id}/{os.path.basename(output_path)}",
        voice_path=voice_path,
        scene_count=len(scenes),
        status="done",
    )


@app.get("/download/{job_id}/{filename}")
def download_video(job_id: str, filename: str):
    if ".." in job_id or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    path = os.path.join(settings.output_dir, job_id, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)


@app.post("/hooks")
def get_hooks(request: VideoRequest):
    from app.services.script import HOOKS_FR, HOOKS_EN
    pool = HOOKS_FR if (request.language or "fr") == "fr" else HOOKS_EN
    return {
        "topic": request.topic,
        "hooks": [h.format(topic=request.topic) for h in pool],
    }


@app.post("/seo")
def get_seo(request: VideoRequest):
    seo = generate_seo(request.topic, language=request.language or "fr")
    return seo
