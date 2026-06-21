import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import settings
from app.models.schemas import VideoRequest, VideoPlan
from app.models.ase_schemas import EpisodeRequest
from app.services.script import generate_script
from app.services.scenes import split_scenes
from app.services.seo import generate_seo
from app.services.video_plan import build_video_plan
from app.jobs.store import create_job, get_job, init as init_jobs, cleanup_old_jobs
from app.jobs.worker import submit, shutdown as shutdown_workers
from app.jobs.tasks import render_video_task, ase_episode_task
from app.jobs.router import router as jobs_router
from app.ase.router import router as ase_router
from app.world.router import router as world_router
from app.utils.helpers import slugify


def _periodic_cleanup(interval_seconds: int = 3600) -> None:
    cleanup_old_jobs(max_age_hours=2)
    t = threading.Timer(interval_seconds, _periodic_cleanup, args=[interval_seconds])
    t.daemon = True
    t.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_jobs()
    _periodic_cleanup()
    yield
    shutdown_workers(wait=False)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for AI-powered short-form video generation",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(ase_router)
app.include_router(world_router)

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


@app.post("/render", status_code=202)
def enqueue_render(request: VideoRequest):
    """
    Enqueues a video render job. Returns immediately with job_id.
    Poll GET /jobs/{job_id}/status to track progress.
    Download the result via the download_url in the completed response.
    """
    if not request.topic.strip():
        raise HTTPException(status_code=422, detail="topic cannot be empty")

    params = {
        "topic": request.topic.strip(),
        "language": request.language or "fr",
        "style": request.style or "viral",
    }
    job = create_job("render", params)
    submit(render_video_task, job["id"], params)

    return {
        "job_id": job["id"],
        "status": "queued",
        "status_url": f"/jobs/{job['id']}/status",
        "poll_hint": "Poll status_url every 5s. download_url appears when status=completed.",
    }


@app.post("/ase/episodes/async", status_code=202)
def enqueue_ase_episode(request: EpisodeRequest):
    """
    Async version of POST /ase/episodes.
    Enqueues episode generation (and optional video render) as a background job.
    """
    params = {
        "story_id": request.story_id,
        "episode_number": request.episode_number,
        "render_video": request.render_video or False,
    }
    job = create_job("ase_episode", params)
    submit(ase_episode_task, job["id"], params)

    return {
        "job_id": job["id"],
        "status": "queued",
        "status_url": f"/jobs/{job['id']}/status",
        "poll_hint": "Poll status_url every 5s. result.episode appears when status=completed.",
    }


@app.get("/download/{render_id}/{filename}")
def download_video(render_id: str, filename: str):
    if ".." in render_id or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    path = os.path.join(settings.output_dir, render_id, filename)
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
