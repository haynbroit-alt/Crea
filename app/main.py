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

    # Latest episode for the zero-RAM CRT player (text + Pollinations URL).
    episodes = world.get("episodes", [])
    last_ep = episodes[-1] if episodes else {}
    last_ep_day = last_ep.get("day", "—")
    last_ep_text = last_ep.get("narrative_text") or last_ep.get("full_script", "")
    last_ep_image = last_ep.get("image_url", "")
    last_ep_json = json.dumps(
        {"text": last_ep_text, "image": last_ep_image}, ensure_ascii=False
    ).replace("<", "\\u003c")

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
  <p style="opacity:.6;font-size:.85em">Surveillance de simulation en temps réel · Ne pas partager · <a href="/docs" style="color:#39ff14">/docs</a> · <a href="/reveil" style="color:#ff3131;text-shadow:0 0 6px #ff3131">▶ L'ARCHIVE QUI S'EFFACE</a></p>
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

  </div>

  <div style="border:2px solid #39ff14;background:#050d05;padding:20px;margin-top:20px;
              box-shadow:0 0 15px rgba(57,255,20,.2);position:relative;border-radius:4px">
    <div style="position:absolute;top:0;left:0;width:100%;height:100%;
                background:linear-gradient(rgba(18,16,16,0) 50%,rgba(0,0,0,.25) 50%),
                           linear-gradient(90deg,rgba(255,0,0,.06),rgba(0,255,0,.02),rgba(0,0,255,.06));
                background-size:100% 4px,6px 100%;pointer-events:none"></div>
    <h3 style="color:#39ff14;font-family:monospace;margin-top:0">
      📟 TRANSMISSION VISUELLE GÉNÉRATIVE — JOUR {last_ep_day}
    </h3>
    <div id="wrapper-image" style="width:100%;max-height:350px;overflow:hidden;
                                   border:1px solid #39ff14;margin-bottom:15px;background:#000">
      <img id="crt-image" src="" alt=""
           style="width:100%;height:auto;display:none;
                  filter:sepia(.2) contrast(1.2) brightness(.9);opacity:.85">
    </div>
    <div id="crt-text" style="color:#39ff14;font-family:'Courier New',monospace;font-size:1.1em;
                              line-height:1.5;min-height:100px;white-space:pre-wrap"></div>
  </div>

  <h3>🧠 SOUVENIRS PERDUS ({len(lost)})</h3>
  <div>{lost_html}</div>

  <h3>🗄️ SHADOW LOG</h3>
  <div class="log-box">{shadow_html}</div>

  <button class="btn" id="advance-btn" type="button">☣️ FORCER L'AVANCE DU MONDE (rendu zéro RAM)</button>
</div>
""" + _GODMODE_SCRIPT.replace("__LAST_EPISODE__", last_ep_json) + """
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


# Client-side CRT player + zero-RAM advance trigger. Kept outside the f-string
# so its braces don't collide with f-string formatting. __LAST_EPISODE__ is
# replaced with the latest episode JSON ({"text": ..., "image": ...}).
_GODMODE_SCRIPT = """
<script>
function playLatestEpisode(narrativeText, imageUrl) {
    const textContainer = document.getElementById('crt-text');
    const imageElement = document.getElementById('crt-image');

    if (imageUrl) {
        imageElement.src = imageUrl;
        imageElement.style.display = 'block';
    }

    textContainer.innerHTML = "";
    let i = 0;
    function typeWriter() {
        if (i < narrativeText.length) {
            textContainer.innerHTML += narrativeText.charAt(i);
            i++;
            setTimeout(typeWriter, 30);
        }
    }
    typeWriter();
}

const __episode = __LAST_EPISODE__;
if (__episode && __episode.text) {
    playLatestEpisode(__episode.text, __episode.image);
} else {
    document.getElementById('crt-text').textContent =
        "Aucune transmission. Cliquez sur le bouton rouge pour générer le premier épisode.";
}

const __btn = document.getElementById('advance-btn');
__btn.addEventListener('click', async function () {
    __btn.disabled = true;
    __btn.textContent = "DÉCLENCHEMENT…";
    try {
        const resp = await fetch('/world/advance', { method: 'POST' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const episode = await resp.json();
        const text = episode.narrative_text || episode.full_script || "";
        playLatestEpisode(text, episode.image_url || "");
        __btn.textContent = "✅ MONDE AVANCÉ — RECHARGEMENT…";
        setTimeout(function () { location.reload(); }, Math.min(text.length * 30 + 1500, 8000));
    } catch (err) {
        __btn.textContent = "❌ ERREUR : " + err.message;
        __btn.disabled = false;
    }
});
</script>"""


def _reveil_payload() -> dict:
    """
    Build the real-world-state payload for the /reveil experience.
    Pure JSON — no rendering, no files. The browser does everything.
    """
    import datetime as _dt
    from app.world.state import get_world
    from app.world.catalog import get_memory, MEMORIES
    from app.world.music import derive_music_params

    world = get_world() or {}
    lost_ids = world.get("lost_memories", [])
    alive_ids = world.get("alive_memories", [m for m in MEMORIES if m not in lost_ids])
    music = derive_music_params(world) if world else {
        "mood": "mystery", "key": "minor", "tempo": 65, "panic": 50, "hope": 50,
        "fog_level": 0, "effects": {"reverb": False, "heartbeat": False,
                                    "music_box": False, "low_pitch": False},
    }

    lost = [
        {
            "id": mid,
            "name": get_memory(mid).get("name", mid),
            "tier": get_memory(mid).get("tier", 1),
            "consequence": get_memory(mid).get("consequence_fr", ""),
        }
        for mid in lost_ids
    ]
    alive = [
        {"id": mid, "name": get_memory(mid).get("name", mid),
         "tier": get_memory(mid).get("tier", 1)}
        for mid in alive_ids
    ]

    return {
        "world_name": world.get("world_name", "La Ville qui oublie"),
        "day": world.get("day", 0),
        "sanity": world.get("collective_sanity", 100),
        "wonder": world.get("wonder_level", 100),
        "infra": world.get("infrastructure_level", 100),
        "corruption": world.get("system_corruption_level", 0.0),
        "date": _dt.date.today().isoformat(),
        "music": music,
        "lost": lost,
        "alive": alive,
        "initialised": bool(world),
    }


@app.get("/reveil", response_class=HTMLResponse)
def reveil_experience():
    """
    « L'Archive qui s'efface » — a full-screen experience where the page itself
    forgets in real time. The corruption level drives an entropy engine that
    erases the archived memories as you read them; a live Web Audio synth
    rebuilds the procedural soundtrack from the world's music params. You may
    save exactly one memory from oblivion. Zero server RAM, zero files.
    """
    payload = json.dumps(_reveil_payload(), ensure_ascii=False).replace("<", "\\u003c")
    html = _REVEIL_TEMPLATE.replace("__PAYLOAD__", payload)
    return HTMLResponse(content=html, status_code=200)


# ─────────────────────────────────────────────────────────────────────────────
# « L'Archive qui s'efface » — full-screen client-side experience.
# Kept as a plain template (not an f-string) so its braces are safe.
# __PAYLOAD__ is replaced with the live world-state JSON.
# ─────────────────────────────────────────────────────────────────────────────
_REVEIL_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>L'Archive qui s'efface</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;background:#02030a;overflow-x:hidden}
  body{font-family:'Courier New',monospace;color:#cfeede;line-height:1.7;
       background:radial-gradient(circle at 50% -10%,#0a1320 0%,#02030a 70%)}
  ::selection{background:#39ff14;color:#02030a}

  /* CRT overlay */
  #crt{position:fixed;inset:0;pointer-events:none;z-index:50;
       background:linear-gradient(rgba(18,16,16,0) 50%,rgba(0,0,0,.28) 50%),
                  linear-gradient(90deg,rgba(255,0,0,.05),rgba(0,255,0,.02),rgba(0,40,255,.05));
       background-size:100% 4px,7px 100%;mix-blend-mode:overlay}
  #vignette{position:fixed;inset:0;pointer-events:none;z-index:51;
       box-shadow:inset 0 0 200px 40px #000;opacity:.7}
  @keyframes flick{0%{opacity:.97}5%{opacity:.85}10%{opacity:.98}50%{opacity:.93}100%{opacity:.97}}
  #wrap{animation:flick .14s infinite}

  /* Boot */
  #boot{position:fixed;inset:0;z-index:100;background:#02030a;padding:6vh 6vw;
        font-size:.92rem;color:#39ff14;text-shadow:0 0 6px #39ff14;overflow:hidden;
        transition:opacity 1.4s ease}
  #boot .ln{white-space:pre-wrap;opacity:0;animation:reveal .01s forwards}
  @keyframes reveal{to{opacity:1}}
  #boot .err{color:#ff3b3b;text-shadow:0 0 6px #ff3b3b}
  #boot .warn{color:#ffb000;text-shadow:0 0 6px #ffb000}
  #boot .dim{opacity:.45}

  /* Archive */
  #archive{max-width:780px;margin:0 auto;padding:9vh 22px 30vh;opacity:0;
           transition:opacity 2s ease}
  .title{font-size:clamp(1.6rem,6vw,3rem);color:#fff;letter-spacing:.04em;
         text-shadow:0 0 14px rgba(57,255,20,.5);margin-bottom:4px;line-height:1.15}
  .sub{color:#5e8a72;font-size:.85rem;margin-bottom:6px}
  .stats{color:#39ff14;font-size:.8rem;opacity:.75;border-top:1px solid rgba(57,255,20,.2);
         border-bottom:1px solid rgba(57,255,20,.2);padding:8px 0;margin:14px 0 34px;
         display:flex;flex-wrap:wrap;gap:14px}
  .stats b{color:#cfeede}

  .mem{margin:0 0 42px;padding-left:16px;border-left:2px solid rgba(57,255,20,.18);
       position:relative;transition:border-color .6s,filter .6s}
  .mem h2{font-size:1.15rem;color:#fff;margin-bottom:10px;font-weight:normal;letter-spacing:.02em}
  .mem .tier{font-size:.7rem;color:#5e8a72;margin-left:8px}
  .mem .body{color:#bcd9c9;min-height:1.6em}
  .mem.saved{border-left-color:#39ff14;filter:drop-shadow(0 0 8px rgba(57,255,20,.35))}
  .mem.saved h2{color:#39ff14;text-shadow:0 0 10px rgba(57,255,20,.6)}
  .mem.gone{opacity:.12}
  .glyph{color:#2f6b46}
  .cursor{display:inline-block;width:.55em;height:1.05em;background:#39ff14;
          margin-left:1px;vertical-align:-2px;animation:blink 1s steps(1) infinite}
  @keyframes blink{50%{opacity:0}}

  /* Save prompt */
  #savebar{position:fixed;left:0;right:0;bottom:0;z-index:60;background:rgba(2,3,10,.92);
           border-top:1px solid rgba(57,255,20,.3);backdrop-filter:blur(4px);
           padding:14px 18px;transform:translateY(110%);transition:transform .8s ease;
           text-align:center}
  #savebar.show{transform:translateY(0)}
  #savebar p{color:#ffb000;font-size:.9rem;margin-bottom:4px;text-shadow:0 0 6px #ffb000}
  #savebar .hint{color:#5e8a72;font-size:.72rem}

  /* Audio + intro gate */
  #gate{position:fixed;inset:0;z-index:120;background:#02030a;display:flex;
        align-items:center;justify-content:center;flex-direction:column;gap:22px;
        text-align:center;padding:24px;transition:opacity 1s ease}
  #gate h1{color:#fff;font-size:clamp(1.4rem,5vw,2.4rem);text-shadow:0 0 16px rgba(57,255,20,.5)}
  #gate p{color:#7fae93;max-width:520px;font-size:.92rem}
  .enter{cursor:pointer;border:1px solid #39ff14;color:#39ff14;background:transparent;
         padding:14px 30px;font-family:inherit;font-size:1rem;letter-spacing:.15em;
         text-shadow:0 0 8px #39ff14;box-shadow:0 0 18px rgba(57,255,20,.25);
         border-radius:3px;transition:.25s}
  .enter:hover{background:#39ff14;color:#02030a;box-shadow:0 0 30px #39ff14}
  #mute{position:fixed;top:14px;right:16px;z-index:70;cursor:pointer;border:1px solid rgba(57,255,20,.4);
        background:rgba(2,3,10,.6);color:#39ff14;font-family:inherit;font-size:.75rem;
        padding:6px 12px;border-radius:3px}
  a.home{position:fixed;top:14px;left:16px;z-index:70;color:#5e8a72;font-size:.72rem;
         text-decoration:none;border-bottom:1px dotted #5e8a72}

  body.fracture #wrap{animation:flick .14s infinite, jitter .25s infinite}
  @keyframes jitter{0%{transform:translate(0,0)}25%{transform:translate(-1px,1px)}
                    50%{transform:translate(1px,-1px)}75%{transform:translate(-1px,-1px)}}
  body.fracture .mem .body{text-shadow:1.5px 0 #ff003c,-1.5px 0 #00e1ff}
</style>
</head>
<body>
<div id="wrap">
  <a class="home" href="/godmode">‹ terminal</a>
  <button id="mute">♪ son : ON</button>

  <div id="gate">
    <h1>L'ARCHIVE QUI S'EFFACE</h1>
    <p>Ce que tu vas lire est en train de disparaître. La Brume efface ces souvenirs
       pendant que tu les parcours. Tu ne pourras en sauver qu'un seul.<br><br>
       <span style="opacity:.6">Mets le son. Reste jusqu'au bout.</span></p>
    <button class="enter" id="enter">▶ ENTRER DANS L'ARCHIVE</button>
  </div>

  <div id="boot"></div>

  <div id="archive">
    <div class="title" id="ar-title"></div>
    <div class="sub" id="ar-sub"></div>
    <div class="stats" id="ar-stats"></div>
    <div id="ar-mems"></div>
  </div>

  <div id="savebar">
    <p id="save-msg">Tu ne peux en retenir qu'un. Touche le souvenir que tu refuses d'oublier.</p>
    <div class="hint">Les autres se dissoudront pour toujours.</div>
  </div>
</div>
<div id="crt"></div>
<div id="vignette"></div>

<script>
const DATA = __PAYLOAD__;

/* ════════════════ AUDIO ENGINE (mirrors derive_music_params) ════════════════ */
const MINOR=[220.0,246.9,261.6,293.7,329.6,349.2,392.0];
const MAJOR=[261.6,293.7,329.6,349.2,392.0,440.0,493.9];
const BOX  =[261.6,277.2,311.1,349.2,370.0];
let AC=null, master=null, audioOn=true, melodyTimer=null, heartTimer=null;

function startAudio(){
  if(AC) return;
  const m=DATA.music||{}; const fx=m.effects||{};
  AC=new (window.AudioContext||window.webkitAudioContext)();
  master=AC.createGain(); master.gain.value=0.0; master.connect(AC.destination);
  master.gain.linearRampToValueAtTime(0.5, AC.currentTime+4);

  // fog reverb = feedback delay
  let sink=master;
  if(fx.reverb){
    const d=AC.createDelay(); d.delayTime.value=0.18;
    const fb=AC.createGain(); fb.gain.value=0.38;
    const wet=AC.createGain(); wet.gain.value=0.5;
    d.connect(fb); fb.connect(d); d.connect(wet); wet.connect(master);
    sink=AC.createGain(); sink.connect(master); sink.connect(d);
  }

  let scale = (m.key==='major')?MAJOR:MINOR;
  if(fx.music_box) scale=BOX;
  const octave = fx.low_pitch?0.5:1.0;

  // continuous drone (root)
  const root=scale[0]*octave/2;
  [0,-0.15,0.15].forEach(det=>{
    const o=AC.createOsc?AC.createOsc():AC.createOscillator();
    o.type='sine'; o.frequency.value=root; o.detune.value=det*100;
    const g=AC.createGain(); g.gain.value=0.06; o.connect(g); g.connect(sink); o.start();
  });

  const beat=60.0/(m.tempo||65);
  function note(){
    if(!AC) return;
    if(Math.random()>0.25){
      let f=scale[Math.floor(Math.random()*scale.length)]*octave;
      if(m.key==='major'&&Math.random()>0.7) f*=2;
      const o=AC.createOscillator();
      o.type=fx.music_box?'triangle':'sine'; o.frequency.value=f;
      const g=AC.createGain(); const t=AC.currentTime;
      const dur=beat*[0.5,1,1.5,2][Math.floor(Math.random()*4)];
      const peak=fx.music_box?0.16:0.12;
      g.gain.setValueAtTime(0.0001,t);
      g.gain.exponentialRampToValueAtTime(peak,t+0.02);
      g.gain.exponentialRampToValueAtTime(0.0001,t+dur);
      o.connect(g); g.connect(sink); o.start(t); o.stop(t+dur+0.05);
    }
    melodyTimer=setTimeout(note, beat*1000*[0.5,1,1.5,2][Math.floor(Math.random()*4)]);
  }
  note();

  // minor-key bass
  if(m.key==='minor'){
    const bscale=scale.slice(0,4).map(f=>f/4*octave);
    (function bass(){
      if(!AC) return;
      const f=bscale[Math.floor(Math.random()*bscale.length)];
      const o=AC.createOscillator(); o.type='sine'; o.frequency.value=f;
      const g=AC.createGain(); const t=AC.currentTime;
      g.gain.setValueAtTime(0.0001,t);
      g.gain.exponentialRampToValueAtTime(0.10,t+0.05);
      g.gain.exponentialRampToValueAtTime(0.0001,t+beat*2);
      o.connect(g); g.connect(sink); o.start(t); o.stop(t+beat*2+0.05);
      setTimeout(bass, beat*2000);
    })();
  }

  // heartbeat
  if(fx.heartbeat){
    const bpm=60+Math.floor((m.panic||60)*0.8);
    function thump(off){
      const o=AC.createOscillator(); o.type='sine'; o.frequency.value=55;
      const g=AC.createGain(); const t=AC.currentTime+off;
      g.gain.setValueAtTime(0.0001,t);
      g.gain.exponentialRampToValueAtTime(0.5,t+0.02);
      g.gain.exponentialRampToValueAtTime(0.0001,t+0.18);
      o.connect(g); g.connect(master); o.start(t); o.stop(t+0.2);
    }
    heartTimer=setInterval(()=>{thump(0);thump(0.13);}, 60000/bpm);
  }
}
function toggleMute(){
  if(!master) return;
  audioOn=!audioOn;
  master.gain.linearRampToValueAtTime(audioOn?0.5:0.0, AC.currentTime+0.4);
  document.getElementById('mute').textContent= audioOn?'♪ son : ON':'♪ son : OFF';
}

/* ════════════════════════════ BOOT SEQUENCE ════════════════════════════ */
function boot(done){
  const C=DATA.corruption||0;
  const lvl = C>0.6?'FRACTURE':C>0.3?'INSTABLE':C>0?'DÉGRADÉ':'NOMINAL';
  const cls = C>0.6?'err':C>0.3?'warn':C>0?'warn':'';
  const lines=[
    ["[BRUME-OS v"+(DATA.day||0)+".0] amorçage du noyau mnémonique...",''],
    ["POST .................................. OK",'dim'],
    ["lecture de l'état du monde : « "+DATA.world_name+" »",''],
    ["  jour ............... "+(DATA.day||'—'),'dim'],
    ["  santé collective .. "+DATA.sanity+"/100",DATA.sanity<40?'warn':'dim'],
    ["  émerveillement .... "+DATA.wonder+"/100",'dim'],
    ["  intégrité système . "+lvl,cls],
    ["analyse de l'archive .................. "+(DATA.lost.length)+" souvenir(s) perdu(s)",''],
    [C>0.3?"AVERTISSEMENT : fuite mnémonique détectée. l'archive se dégrade.":"archive scellée. lecture autorisée.",C>0.3?'warn':''],
    [C>0.6?"ERREUR CRITIQUE : la Brume a franchi le pare-feu. // qui lit ceci ?":"montage de l'interface...",C>0.6?'err':'dim'],
    ["",''],
    ["> ouverture de l'archive_______",''],
  ];
  const box=document.getElementById('boot'); let i=0;
  (function next(){
    if(i>=lines.length){ setTimeout(done,700); return; }
    const [txt,c]=lines[i];
    const p=document.createElement('div');
    p.className='ln'+(c?(' '+c):''); p.textContent=txt; box.appendChild(p);
    i++; setTimeout(next, 80+Math.random()*220);
  })();
}

/* ═══════════════════════ FORGETTING ENGINE ═══════════════════════ */
const GLYPHS="░▒▓█▚▞╳·•∴⌁¦".split("");
const decayers=[]; // {el, chars, alive, saved}
let savedOne=false;

function renderArchive(){
  document.getElementById('ar-title').textContent = DATA.world_name;
  document.getElementById('ar-sub').textContent =
    "Archive mnémonique — Jour "+DATA.day+" · "+DATA.date;
  const C=DATA.corruption||0;
  document.getElementById('ar-stats').innerHTML =
    "<span>santé <b>"+DATA.sanity+"</b></span>"+
    "<span>émerveillement <b>"+DATA.wonder+"</b></span>"+
    "<span>corruption <b style='color:"+(C>0.3?'#ff3b3b':'#39ff14')+"'>"+
      (C*100).toFixed(0)+"%</b></span>"+
    "<span>perdus <b>"+DATA.lost.length+"</b></span>";

  const host=document.getElementById('ar-mems');
  if(!DATA.initialised || DATA.lost.length===0){
    host.innerHTML="<div class='mem'><h2>L'archive est vide.</h2>"+
      "<div class='body'>La Brume n'a encore rien pris. Reviens quand la ville aura commencé à oublier.</div></div>";
    return;
  }

  let idx=0;
  (function addOne(){
    if(idx>=DATA.lost.length){ setTimeout(armSave, 1200); return; }
    const m=DATA.lost[idx];
    const card=document.createElement('div'); card.className='mem'; card.dataset.id=m.id;
    const tierTxt=['','sensoriel','social','existentiel'][m.tier]||'';
    card.innerHTML="<h2>"+m.name+"<span class='tier'>// "+tierTxt+"</span></h2>"+
                   "<div class='body'></div>";
    host.appendChild(card);
    const body=card.querySelector('.body');
    typewrite(body, m.consequence, ()=>{
      decayers.push({el:body, chars:m.consequence.split(""), saved:false, card:card});
    });
    idx++;
    setTimeout(addOne, Math.min(m.consequence.length*22+900, 5200));
  })();
}

function typewrite(el, text, cb){
  let i=0; el.innerHTML="<span class='cursor'></span>";
  (function step(){
    if(i<text.length){
      el.innerHTML=text.slice(0,i+1)+"<span class='cursor'></span>";
      i++; setTimeout(step, 16+Math.random()*22);
    } else { el.textContent=text; cb&&cb(); }
  })();
}

function decayTick(){
  const C=DATA.corruption||0;
  // base entropy even at 0 corruption (gentle), scaled hard by corruption
  const intensity = 0.25 + C*3.2;
  decayers.forEach(d=>{
    if(d.saved) return;
    const reps = Math.max(1, Math.round(intensity));
    for(let r=0;r<reps;r++){
      const live=[]; for(let k=0;k<d.chars.length;k++){ if(d.chars[k]!==''&&d.chars[k]!==' ') live.push(k); }
      if(live.length===0){ d.card.classList.add('gone'); return; }
      const j=live[Math.floor(Math.random()*live.length)];
      // two-stage: letter -> glyph -> void
      if(d.chars[j].length===1 && GLYPHS.indexOf(d.chars[j])===-1 && Math.random()>0.4){
        d.chars[j]=GLYPHS[Math.floor(Math.random()*GLYPHS.length)];
      } else {
        d.chars[j]='';
      }
    }
    // render with glyph styling
    let html="";
    for(const c of d.chars){
      if(c==='') html+=" ";
      else if(GLYPHS.indexOf(c)!==-1) html+="<span class='glyph'>"+c+"</span>";
      else html+= (c==='<'?'&lt;':c==='>'?'&gt;':c==='&'?'&amp;':c);
    }
    d.el.innerHTML=html;
  });
}

/* ═══════════════════════ SAVE ONE MEMORY ═══════════════════════ */
function armSave(){
  if(!DATA.initialised || DATA.lost.length===0) return;
  document.getElementById('savebar').classList.add('show');
  decayers.forEach(d=>{
    d.card.style.cursor='pointer';
    d.card.addEventListener('click', ()=>{
      if(savedOne) return;
      savedOne=true;
      d.saved=true; d.card.classList.add('saved');
      // restore the saved memory's text in full
      d.chars=d.card.dataset.fulltext? d.card.dataset.fulltext.split("") : d.chars;
      d.el.textContent = DATA.lost.find(x=>x.id===d.card.dataset.id).consequence;
      document.getElementById('save-msg').textContent =
        "« "+ d.card.querySelector('h2').childNodes[0].textContent.trim() +" » est sauvé. Le reste appartient à la Brume.";
      // accelerate the death of all others
      DATA.corruption = Math.max(DATA.corruption, 0.8);
      document.body.classList.add('fracture');
    }, {once:false});
  });
}

/* ═══════════════════════ 4TH WALL ═══════════════════════ */
function fourthWall(){
  if((DATA.corruption||0)<=0.6) return;
  document.body.classList.add('fracture');
  const host=document.getElementById('ar-mems');
  const msgs=[
    "// la Brume a fini avec la ville.",
    "// elle te regarde, maintenant. toi, "+DATA.date+".",
    "// tu crois lire une histoire. tu es dans l'archive.",
    "// un jour quelqu'un ouvrira ce fichier et ne se souviendra pas de toi non plus.",
  ];
  let k=0;
  function whisper(){
    if(k>=msgs.length) return;
    const p=document.createElement('div'); p.className='mem';
    p.style.borderLeftColor='#ff3b3b';
    p.innerHTML="<div class='body' style='color:#ff6b6b;text-shadow:0 0 8px #ff3b3b'></div>";
    host.appendChild(p);
    typewrite(p.querySelector('.body'), msgs[k], null);
    k++; setTimeout(whisper, 4200);
  }
  setTimeout(whisper, 6000);
}

/* ════════════════════════════ INIT ════════════════════════════ */
document.getElementById('mute').addEventListener('click', toggleMute);
document.getElementById('enter').addEventListener('click', ()=>{
  startAudio();
  const gate=document.getElementById('gate');
  gate.style.opacity='0'; setTimeout(()=>gate.style.display='none', 1000);
  boot(()=>{
    const b=document.getElementById('boot');
    b.style.opacity='0'; setTimeout(()=>b.style.display='none',1400);
    document.getElementById('archive').style.opacity='1';
    renderArchive();
    fourthWall();
    setInterval(decayTick, 900);
  });
});
</script>
</body>
</html>"""
