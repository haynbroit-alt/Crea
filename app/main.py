import json
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

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

os.makedirs(settings.output_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.output_dir), name="media")

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
    from app.services.ai_client import is_available
    return {"status": "ok", "ai_narrative": is_available()}


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
def download_file(render_id: str, filename: str):
    if ".." in render_id or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    path = os.path.join(settings.output_dir, render_id, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    media = "audio/wav" if filename.endswith(".wav") else "video/mp4"
    return FileResponse(path, media_type=media, filename=filename)


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


@app.get("/godmode", response_class=HTMLResponse)
def god_mode_dashboard():
    """
    Retro CRT control terminal. Shows live world state, shadow_log, and a
    one-click pipeline trigger. Do NOT share this URL publicly.
    """
    from app.world.state import get_world
    _last_ep: dict = {}
    try:
        with open("data/last_episode.json", encoding="utf-8") as _f:
            _last_ep = json.load(_f)
    except Exception:
        pass
    from app.world.catalog import get_memory
    from app.services.ai_client import is_available
    from app.services.supabase_store import is_configured as sb_configured

    world = get_world() or {}
    day = world.get("day", "—")
    sanity = world.get("collective_sanity", "—")
    infra = world.get("infrastructure_level", "—")
    wonder = world.get("wonder_level", "—")
    corruption = world.get("system_corruption_level", 0.0)
    voting_open = world.get("voting_open", False)
    votes = world.get("vote_counts", {"A": 0, "B": 0})
    lost = world.get("lost_memories", [])
    shadow = world.get("shadow_log", [])
    ai_on = is_available()
    sb_on = sb_configured()

    lost_html = "".join(
        f"<span class='badge'>{get_memory(m).get('name', m)}</span>"
        for m in lost
    ) or "<span class='badge dim'>aucun</span>"

    shadow_html = "".join(
        f"<p class='log-line'>{line}</p>" for line in (shadow or ["Aucune anomalie détectée."])
    )

    dilemma = world.get("current_dilemma") or {}
    opt_a = dilemma.get("option_A", {})
    opt_b = dilemma.get("option_B", {})
    dilemma_html = (
        f"<p>A : Protéger <b>{opt_a.get('label_protect','?')}</b> / Sacrifier {opt_a.get('label_sacrifice','?')}</p>"
        f"<p>B : Protéger <b>{opt_b.get('label_protect','?')}</b> / Sacrifier {opt_b.get('label_sacrifice','?')}</p>"
        f"<p>Votes — A: {votes.get('A',0)} · B: {votes.get('B',0)} · "
        f"Vote ouvert: {'OUI' if voting_open else 'NON'}</p>"
    ) if dilemma else "<p>Aucun dilemme actif.</p>"

    last_ep_url = _last_ep.get("url", "")
    last_ep_day = _last_ep.get("day", "—")

    corruption_pct = f"{corruption * 100:.1f}%"
    corruption_colour = "#ff3131" if corruption > 0.3 else ("#ffb000" if corruption > 0 else "#39ff14")
    corruption_status = (
        "FRACTURE — 4E MUR BRISÉ" if corruption > 0.6
        else "VOTES FANTÔMES ACTIFS" if corruption > 0.3
        else "INDICES NARRATIFS ACTIFS" if corruption > 0
        else "INTÉGRITÉ INTACTE"
    )

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>La Ville qui oublie — Terminal de Contrôle</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0a0a12;color:#39ff14;font-family:'Courier New',monospace;padding:20px;
         text-shadow:0 0 5px #39ff14;line-height:1.6}}
    h1{{color:#ff3131;text-shadow:0 0 8px #ff3131;margin-bottom:4px;font-size:1.2em}}
    h3{{margin:12px 0 6px;font-size:.95em;opacity:.8}}
    .terminal{{border:2px solid #39ff14;padding:20px;background:#05050a;
               box-shadow:0 0 20px rgba(57,255,20,.15);border-radius:4px;max-width:900px;margin:auto}}
    hr{{border-color:#39ff14;opacity:.3;margin:12px 0}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:14px 0}}
    .card{{border:1px dashed #39ff14;padding:14px;background:rgba(57,255,20,.04);border-radius:3px}}
    .card p{{margin:4px 0;font-size:.9em}}
    .badge{{background:#1a1a2e;border:1px solid #39ff14;color:#39ff14;
            padding:2px 7px;margin:2px;display:inline-block;font-size:.8em;border-radius:2px}}
    .badge.dim{{opacity:.4}}
    .log-box{{background:#000;border:1px solid #2a2a3a;height:140px;overflow-y:auto;
              padding:10px;color:#ffb000;text-shadow:0 0 4px #ffb000;border-radius:3px;margin-top:6px}}
    .log-line{{margin:3px 0;font-size:.8em}}
    .big{{font-size:1.6em;font-weight:bold}}
    .btn{{display:block;background:#ff3131;color:#000;border:none;padding:12px;width:100%;
          font-family:'Courier New',monospace;font-weight:bold;cursor:pointer;font-size:1em;
          box-shadow:0 0 12px #ff3131;border-radius:3px;margin-top:10px;text-transform:uppercase}}
    .btn:hover{{background:#fff;box-shadow:0 0 20px #fff}}
    .status-ok{{color:#39ff14}}.status-warn{{color:#ffb000}}.status-err{{color:#ff3131}}
  </style>
</head>
<body>
<div class="terminal">
  <h1>[PROJET_BRUME] SYSTEM_OVERRIDE_CONNECTED</h1>
  <p style="opacity:.6;font-size:.85em">Surveillance de simulation en temps réel · Ne pas partager · <a href="/docs" style="color:#39ff14">/docs</a></p>
  <hr>

  <div class="grid">
    <div class="card">
      <h3>📊 ÉTAT DU MONDE</h3>
      <p>Jour : <b>{day}</b></p>
      <p>Santé collective : <b>{sanity}/100</b></p>
      <p>Émerveillement : <b>{wonder}/100</b></p>
      <p>Infrastructure : <b>{infra}/100</b></p>
      <p>Claude IA : <span class="{'status-ok' if ai_on else 'status-err'}">{'ACTIF' if ai_on else 'HORS LIGNE'}</span></p>
      <p>Supabase : <span class="{'status-ok' if sb_on else 'status-warn'}">{'CONNECTÉ' if sb_on else 'LOCAL ONLY'}</span></p>
    </div>
    <div class="card">
      <h3>⚠️ CORRUPTION SYSTÈME</h3>
      <p class="big" style="color:{corruption_colour}">{corruption_pct}</p>
      <p style="color:{corruption_colour}">{corruption_status}</p>
    </div>
    <div class="card">
      <h3>🗳️ DILEMME ACTIF</h3>
      {dilemma_html}
    </div>
  </div>

  {'<div class="card" style="grid-column:span 3"><h3>🎬 DERNIER ÉPISODE — JOUR ' + str(last_ep_day) + '</h3><video controls style="width:100%;border:1px solid #39ff14;background:#000;margin-top:8px;border-radius:3px"><source src="' + last_ep_url + '" type="video/mp4">Votre navigateur ne supporte pas la lecture.</video></div>' if last_ep_url else '<div class="card" style="opacity:.4"><h3>🎬 AUCUN ÉPISODE RENDU</h3><p>Cliquez sur le bouton rouge pour générer le premier épisode.</p></div>'}
  </div>

  <h3>🧠 SOUVENIRS PERDUS ({len(lost)})</h3>
  <div>{lost_html}</div>

  <h3>🗄️ SHADOW LOG</h3>
  <div class="log-box">{shadow_html}</div>

  <form action="/world/advance?render=true" method="post"
        onsubmit="this.querySelector('button').textContent='DÉCLENCHEMENT…';return true;">
    <button class="btn" type="submit">☣️ FORCER L'AVANCE DU MONDE (pipeline complet)</button>
  </form>
</div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)
