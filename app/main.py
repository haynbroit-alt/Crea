from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.schemas import VideoRequest, VideoPlan
from app.services.script import generate_script
from app.services.scenes import split_scenes
from app.services.seo import generate_seo
from app.services.video_plan import build_video_plan

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
