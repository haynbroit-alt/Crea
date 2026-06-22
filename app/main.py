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

  <button class="btn" id="init-btn" type="button"
          style="background:#39ff14;box-shadow:0 0 12px #39ff14;margin-bottom:8px">🌱 INITIALISER LE MONDE (Jour 1)</button>
  <button class="btn" id="advance-btn" type="button">☣️ FORCER L'AVANCE DU MONDE (rendu zéro RAM)</button>
  <button class="btn" id="publish-btn" type="button"
          style="background:#ff00aa;box-shadow:0 0 12px #ff00aa;margin-top:8px">🎬 PUBLIER UN SHORT YOUTUBE (avance + rendu + upload)</button>
  <p id="publish-out" style="font-size:.8em;opacity:.7;margin-top:6px;min-height:1.1em"></p>

  <div style="margin-top:18px;border-top:1px solid rgba(57,255,20,.25);padding-top:12px">
    <label style="opacity:.55;font-size:.8em">invite de commande</label>
    <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
      <span style="color:#39ff14">&gt;</span>
      <input id="cmd" type="text" autocomplete="off" spellcheck="false"
             placeholder="_"
             style="flex:1;background:#000;border:1px solid rgba(57,255,20,.35);color:#39ff14;
                    font-family:'Courier New',monospace;padding:8px 10px;border-radius:3px;
                    text-shadow:0 0 5px #39ff14;outline:none;letter-spacing:.1em">
    </div>
    <p id="cmd-out" style="font-size:.78em;opacity:.6;margin-top:6px;min-height:1.2em"></p>
  </div>
</div>
""" + _GODMODE_SCRIPT.replace("__LAST_EPISODE__", last_ep_json).replace(
        "__SECRET__", json.dumps(_residue_key(world), ensure_ascii=False)
    ) + """
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

// POST helper that surfaces the server's error detail instead of a bare status.
async function __post(path) {
    const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        redirect: 'follow',
    });
    let data = null;
    try { data = await resp.json(); } catch (e) {}
    if (!resp.ok) {
        const detail = (data && data.detail) ? data.detail : ('HTTP ' + resp.status);
        const err = new Error(detail); err.status = resp.status; throw err;
    }
    return data;
}

const __initBtn = document.getElementById('init-btn');
if (__initBtn) {
    __initBtn.addEventListener('click', async function () {
        __initBtn.disabled = true;
        __initBtn.textContent = "INITIALISATION…";
        try {
            await __post('/world/init');
            __initBtn.textContent = "✅ MONDE INITIALISÉ — RECHARGEMENT…";
            setTimeout(function () { location.reload(); }, 900);
        } catch (err) {
            __initBtn.textContent = "❌ " + err.message;
            __initBtn.disabled = false;
        }
    });
}

const __btn = document.getElementById('advance-btn');
__btn.addEventListener('click', async function () {
    __btn.disabled = true;
    __btn.textContent = "DÉCLENCHEMENT…";
    try {
        let episode;
        try {
            episode = await __post('/world/advance');
        } catch (err) {
            // The world may not be initialised yet — bootstrap, then retry once.
            if (/initialis/i.test(err.message) || err.status === 400) {
                __btn.textContent = "MONDE ABSENT — INITIALISATION…";
                await __post('/world/init');
                episode = await __post('/world/advance');
            } else {
                throw err;
            }
        }
        const text = episode.narrative_text || episode.full_script || "";
        playLatestEpisode(text, episode.image_url || "");
        __btn.textContent = "✅ MONDE AVANCÉ — RECHARGEMENT…";
        setTimeout(function () { location.reload(); }, Math.min(text.length * 30 + 1500, 8000));
    } catch (err) {
        __btn.textContent = "❌ ERREUR : " + err.message;
        __btn.disabled = false;
    }
});

// ── PUBLICATION YOUTUBE SHORT (rendu ffmpeg + upload en arrière-plan) ──
const __pubBtn = document.getElementById('publish-btn');
const __pubOut = document.getElementById('publish-out');
if (__pubBtn) {
    __pubBtn.addEventListener('click', async function () {
        __pubBtn.disabled = true;
        __pubBtn.textContent = "🎬 FORGE LANCÉE…";
        try {
            const job = await __post('/world/publish');
            __pubOut.textContent = "Job " + job.job_id + " — rendu en cours (1–3 min)…";
            const statusUrl = job.status_url;
            const poll = setInterval(async function () {
                try {
                    const r = await fetch(statusUrl, { headers: { 'Accept': 'application/json' } });
                    const s = await r.json();
                    if (s.status === 'completed') {
                        clearInterval(poll);
                        const res = s.result || {};
                        const yt = res.youtube;
                        if (yt && yt.url) {
                            __pubOut.innerHTML = "✅ Publié : <a href='" + yt.url + "' target='_blank' style='color:#39ff14'>" + yt.url + "</a>";
                        } else if (res.media_url) {
                            __pubOut.innerHTML = "✅ Vidéo rendue (upload YouTube non configuré) : <a href='" + res.media_url + "' target='_blank' style='color:#39ff14'>voir</a>";
                        } else {
                            __pubOut.textContent = "✅ Terminé (aucune vidéo rendue — ffmpeg indisponible ?).";
                        }
                        __pubBtn.textContent = "🎬 PUBLIER UN AUTRE SHORT";
                        __pubBtn.disabled = false;
                    } else if (s.status === 'failed') {
                        clearInterval(poll);
                        __pubOut.textContent = "❌ Échec : " + (s.error || 'inconnu');
                        __pubBtn.textContent = "🎬 RÉESSAYER";
                        __pubBtn.disabled = false;
                    }
                } catch (e) {}
            }, 4000);
        } catch (err) {
            __pubOut.textContent = "❌ " + err.message;
            __pubBtn.textContent = "🎬 RÉESSAYER";
            __pubBtn.disabled = false;
        }
    });
}

// ── L'EFFET PARADOXE : la clé enfouie dans l'oubli ouvre la faille ──
// __SECRET__ est dérivée de l'état du monde côté serveur (zéro stockage) — la
// même clé est semée en fragments dans /reveil. Elle mute quand la ville oublie.
const __SECRET = __norm(__SECRET__);
const __cmd = document.getElementById('cmd');
const __out = document.getElementById('cmd-out');
function __norm(s){ return (s||"").toUpperCase().replace(/[^A-Z]/g, ""); }
if (__cmd) {
    __cmd.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        const v = __norm(__cmd.value);
        if (__SECRET && v === __SECRET) {
            triggerParadox();
        } else if (v === 'AIDE' || v === 'HELP') {
            __out.textContent = __SECRET
                ? ("rassemble les " + __SECRET.length + " cicatrices laissées par les souvenirs effacés dans /reveil, puis remets-les dans l'ordre.")
                : "la ville n'a encore rien oublié. aucune cicatrice à rassembler.";
        } else if (v.length) {
            __out.textContent = "commande inconnue. la Brume n'a rien retenu.";
            __cmd.value = "";
        }
    });
}

function triggerParadox() {
    __out.textContent = "⌁ FAILLE DÉTECTÉE — le temps se fige…";
    __cmd.disabled = true;
    // a strident frozen note
    try {
        const ac = new (window.AudioContext || window.webkitAudioContext)();
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = 'sawtooth'; o.frequency.value = 1760;
        g.gain.value = 0.0001;
        g.gain.exponentialRampToValueAtTime(0.18, ac.currentTime + 0.05);
        o.connect(g); g.connect(ac.destination); o.start();
    } catch (e) {}
    // freeze + collapse the screen, then open the hidden route
    const veil = document.createElement('div');
    veil.style.cssText = "position:fixed;inset:0;z-index:9999;background:#000;opacity:0;" +
        "transition:opacity 2.2s ease;mix-blend-mode:normal";
    document.body.appendChild(veil);
    document.body.style.transition = "filter 2s ease, transform 2s ease";
    document.body.style.filter = "invert(1) hue-rotate(90deg) contrast(2)";
    document.body.style.transform = "scale(1.04)";
    requestAnimationFrame(() => { veil.style.opacity = "1"; });
    setTimeout(function () { location.href = "/paradox"; }, 2400);
}
</script>"""


def _residue_key(world: dict) -> str:
    """
    Derive the ghost-residue ARG key from world state — deterministically, with
    zero stored bytes. One letter per lost memory, drawn from that memory's own
    name, so the key is literally assembled from the debris of what the city
    forgot. Length == number of lost memories → always solvable (each death
    reveals exactly one letter). The same JSON yields the same key on /reveil
    (which seeds the fragments) and /godmode (which validates), and it rotates
    as the world advances.
    """
    import unicodedata
    from app.world.catalog import get_memory

    def _ascii_upper(s: str) -> str:
        no_accent = "".join(
            c for c in unicodedata.normalize("NFD", s)
            if unicodedata.category(c) != "Mn"
        )
        return "".join(c for c in no_accent.upper() if "A" <= c <= "Z")

    day = world.get("day", 0)
    letters = []
    for i, mid in enumerate(world.get("lost_memories", [])):
        alpha = _ascii_upper(get_memory(mid).get("name", mid)) or "BRUME"
        h = 2166136261
        for ch in f"{mid}|{day}|{i}":               # deterministic per memory/day
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
        letters.append(alpha[h % len(alpha)])
    return "".join(letters)


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
        "secret": _residue_key(world),
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


@app.get("/paradox", response_class=HTMLResponse)
def paradox():
    """
    The hidden room. Reached only by recovering the ghost-residue code in /reveil
    and typing it into the /godmode command prompt. Here the narrator stops being
    the city and becomes the thing narrating it — and realises where it is.
    Zero RAM, zero files.
    """
    import datetime as _dt
    from app.world.state import get_world
    world = get_world() or {}
    payload = json.dumps({
        "date": _dt.date.today().isoformat(),
        "world_name": world.get("world_name", "La Ville qui oublie"),
        "day": world.get("day", 0),
        "sanity": world.get("collective_sanity", 100),
        "lost": len(world.get("lost_memories", [])),
    }, ensure_ascii=False).replace("<", "\\u003c")
    return HTMLResponse(content=_PARADOX_TEMPLATE.replace("__PAYLOAD__", payload),
                        status_code=200)


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

  /* ── DOM LIQUEFACTION : l'écran malade (variables pilotées en JS) ── */
  :root{--shX:0px; --shY:0px; --hue:0deg; --sat:1; --bleed:0px;
        --tilt:0deg; --spread:0em}
  #wrap{filter:hue-rotate(var(--hue)) saturate(var(--sat))}
  body.melting .title,
  body.melting .stats,
  body.melting .sub{transform:translate(var(--shX),var(--shY)) rotate(var(--tilt));
                    letter-spacing:var(--spread)}
  body.melting .mem{transform:translate(calc(var(--shX) * var(--m,1)),
                                        calc(var(--shY) * var(--m,1)))
                              rotate(calc(var(--tilt) * var(--m,1)))}
  body.melting .mem .body{text-shadow:var(--bleed) 0 #ff8a00,
                                      calc(-1 * var(--bleed)) 0 #fffbe6}
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
let _sink=null, _scale=MINOR, _octave=1.0;

/* ── BIO-MUSIQUE : la bande-son réagit au corps du joueur ── */
const bio={vel:0, lastMove:Date.now(), idle:0};
window.addEventListener('mousemove', (e)=>{
  const dx=e.movementX||0, dy=e.movementY||0;
  bio.vel=Math.min(1, bio.vel*0.7 + Math.hypot(dx,dy)/55);
  bio.lastMove=Date.now();
});
window.addEventListener('touchmove', ()=>{ bio.vel=Math.min(1,bio.vel+0.25); bio.lastMove=Date.now(); }, {passive:true});
setInterval(()=>{
  bio.vel*=0.85;                                  // panic cools down
  const since=(Date.now()-bio.lastMove)/1000;     // seconds idle
  bio.idle = Math.max(0, Math.min(1, (since-5)/12)); // asleep after ~5s, full at ~17s
}, 250);

// the agony cry of a dying memory (hover)
function cry(card){
  if(!AC || card.classList.contains('saved') || card.classList.contains('gone')) return;
  const f=_scale[_scale.length-1]*_octave*2*(1 - bio.idle*0.4);
  const o=AC.createOscillator(); o.type='sine'; o.frequency.value=f;
  const g=AC.createGain(); const t=AC.currentTime;
  g.gain.setValueAtTime(0.0001,t);
  g.gain.exponentialRampToValueAtTime(0.09,t+0.04);
  g.gain.exponentialRampToValueAtTime(0.0001,t+0.9);
  o.frequency.exponentialRampToValueAtTime(f*0.82, t+0.9); // a falling wail
  o.connect(g); g.connect(_sink||master); o.start(t); o.stop(t+1.0);
}

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

  _sink=sink;
  let scale = (m.key==='major')?MAJOR:MINOR;
  if(fx.music_box) scale=BOX;
  const octave = fx.low_pitch?0.5:1.0;
  _scale=scale; _octave=octave;

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
    // when the player goes idle, the music falls asleep: rarer, deeper, slower
    const playChance = 0.75 * (1 - bio.idle*0.55);
    if(Math.random()<playChance){
      let f=scale[Math.floor(Math.random()*scale.length)]*octave;
      if(m.key==='major'&&Math.random()>0.7) f*=2;
      f *= (1 - bio.idle*0.5);                       // sinks into the fog
      const o=AC.createOscillator();
      o.type=fx.music_box?'triangle':'sine'; o.frequency.value=f;
      const g=AC.createGain(); const t=AC.currentTime;
      const dur=beat*[0.5,1,1.5,2][Math.floor(Math.random()*4)]*(1+bio.idle*1.4);
      const peak=(fx.music_box?0.16:0.12)*(1 - bio.idle*0.3);
      g.gain.setValueAtTime(0.0001,t);
      g.gain.exponentialRampToValueAtTime(peak,t+0.02);
      g.gain.exponentialRampToValueAtTime(0.0001,t+dur);
      o.connect(g); g.connect(sink); o.start(t); o.stop(t+dur+0.05);
    }
    // frantic mouse → notes crowd together; abandon → they drift apart
    const gap = beat*1000*[0.5,1,1.5,2][Math.floor(Math.random()*4)]
                * (1 + bio.idle*1.6) / (1 + bio.vel*0.8);
    melodyTimer=setTimeout(note, gap);
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

  // heartbeat — accelerates with the player's panic (mouse velocity)
  if(fx.heartbeat){
    const baseBpm=60+Math.floor((m.panic||60)*0.8);
    function thump(off){
      const o=AC.createOscillator(); o.type='sine'; o.frequency.value=55;
      const g=AC.createGain(); const t=AC.currentTime+off;
      g.gain.setValueAtTime(0.0001,t);
      g.gain.exponentialRampToValueAtTime(0.5,t+0.02);
      g.gain.exponentialRampToValueAtTime(0.0001,t+0.18);
      o.connect(g); g.connect(master); o.start(t); o.stop(t+0.2);
    }
    (function beatLoop(){
      if(!AC) return;
      thump(0); thump(0.13);
      const bpm=baseBpm*(1 + bio.vel*1.5) / (1 + bio.idle*0.5);
      heartTimer=setTimeout(beatLoop, 60000/bpm);
    })();
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

/* ── RÉSIDUS FANTÔMES (ARG) : l'oubli laisse des cicatrices ── */
// La clé est dérivée de l'état du monde (DATA.secret) : une lettre par souvenir,
// tirée de son propre nom. Chaque mort révèle SA lettre, à SA position. Rassemblées
// dans l'ordre, elles ouvrent la faille /godmode. Zéro octet stocké côté serveur.
const SECRET=(DATA.secret||"");
const _collected=new Array(SECRET.length).fill(null);
function revealFragment(pos, memName){
  if(pos<0 || pos>=SECRET.length || _collected[pos]!==null) return;
  const ch=SECRET[pos]; _collected[pos]=ch;
  document.body.dataset["residu"+(pos+1)]=ch;
  console.log("%c[RÉSIDU] cicatrice "+(pos+1)+"/"+SECRET.length+
              " — « "+memName+" » a laissé : "+ch,
              "color:#39ff14;font-family:monospace;text-shadow:0 0 4px #39ff14");
  if(_collected.every(x=>x!==null)){
    console.log("%c[ARCHIVE] toutes les cicatrices sont là. remises dans l'ordre :\n  »  "
      +_collected.join("")+"  «\ntape ceci dans le terminal /godmode pour ouvrir la faille.",
      "color:#ffb000;font-family:monospace;font-size:14px;text-shadow:0 0 6px #ffb000");
  }
}

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
    const pos=idx;                         // capture this memory's key position
    const m=DATA.lost[pos];
    const card=document.createElement('div'); card.className='mem'; card.dataset.id=m.id;
    card.style.setProperty('--m', (0.4 + Math.random()*1.2).toFixed(2));
    const tierTxt=['','sensoriel','social','existentiel'][m.tier]||'';
    card.innerHTML="<h2>"+m.name+"<span class='tier'>// "+tierTxt+"</span></h2>"+
                   "<div class='body'></div>";
    host.appendChild(card);
    const body=card.querySelector('.body');
    card.addEventListener('mouseenter', ()=>cry(card));
    typewrite(body, m.consequence, ()=>{
      decayers.push({el:body, chars:m.consequence.split(""), saved:false,
                     card:card, name:m.name, dead:false, pos:pos});
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
      if(live.length===0){
        d.card.classList.add('gone');
        if(!d.dead){ d.dead=true; revealFragment(d.pos, d.name||'?'); }
        return;
      }
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

/* ═══════════════════ LIQUÉFACTION DU DOM (l'écran malade) ═══════════════════ */
function liquefy(){
  // intensity rises with world corruption AND the player's panic
  const C=DATA.corruption||0;
  const k=Math.min(1, C + bio.vel*0.4);
  const rs=document.documentElement.style;
  rs.setProperty('--shX', (Math.random()*2-1)*2.2*k + 'px');
  rs.setProperty('--shY', (Math.random()*2-1)*2.2*k + 'px');
  rs.setProperty('--tilt', (Math.random()*2-1)*0.5*k + 'deg');
  rs.setProperty('--bleed', (Math.random()*3)*k + 'px');
  rs.setProperty('--spread', (Math.random()*0.06)*k + 'em');
  // the matrix-green slowly bleeds toward toxic orange / sickly white as it dies
  rs.setProperty('--hue', (k*48 + Math.sin(Date.now()/700)*6*k).toFixed(1) + 'deg');
  rs.setProperty('--sat', (1 - k*0.45 + Math.random()*0.1*k).toFixed(2));
}

/* ════════════════════════════ INIT ════════════════════════════ */
document.getElementById('mute').addEventListener('click', toggleMute);
document.getElementById('enter').addEventListener('click', ()=>{
  startAudio();
  const gate=document.getElementById('gate');
  gate.style.opacity='0'; setTimeout(()=>gate.style.display='none', 1000);
  // ARG breadcrumb for those who read the source
  document.body.appendChild(document.createComment(
    " RESIDU // l'oubli laisse des cicatrices. rassemble-les. la faille attend dans le terminal. "));
  console.log("%cLa Brume oublie. Mais regarde la console — certains souvenirs y laissent une trace.",
              "color:#5e8a72;font-family:monospace");
  boot(()=>{
    const b=document.getElementById('boot');
    b.style.opacity='0'; setTimeout(()=>b.style.display='none',1400);
    document.getElementById('archive').style.opacity='1';
    document.body.classList.add('melting');
    renderArchive();
    fourthWall();
    setInterval(decayTick, 900);
    setInterval(liquefy, 120);
  });
});
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# « /paradox » — the hidden room. Plain template; __PAYLOAD__ is replaced.
# ─────────────────────────────────────────────────────────────────────────────
_PARADOX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>// PARADOXE</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;background:#000;overflow:hidden}
  body{font-family:'Courier New',monospace;color:#e8e8e8;display:flex;
       align-items:center;justify-content:center;padding:6vw}
  #scan{position:fixed;inset:0;pointer-events:none;z-index:5;
        background:linear-gradient(rgba(0,0,0,0) 50%,rgba(255,255,255,.03) 50%);
        background-size:100% 3px}
  #frame{max-width:680px;width:100%;z-index:2}
  #freeze{position:fixed;inset:0;z-index:1;
          background:radial-gradient(circle at 50% 50%,rgba(255,255,255,.04),#000 70%)}
  .line{white-space:pre-wrap;font-size:clamp(.95rem,2.6vw,1.15rem);line-height:1.9;
        margin:0;min-height:1.9em;letter-spacing:.02em}
  .who{color:#5e8a72;font-size:.78rem;letter-spacing:.25em;margin:26px 0 4px;text-transform:uppercase}
  .cur{display:inline-block;width:.55em;height:1.05em;background:#e8e8e8;
       margin-left:2px;vertical-align:-2px;animation:bl 1.1s steps(1) infinite}
  @keyframes bl{50%{opacity:0}}
  #gate2{position:fixed;inset:0;z-index:30;background:#000;display:flex;
         align-items:center;justify-content:center;flex-direction:column;gap:24px;
         text-align:center;padding:24px;cursor:pointer;transition:opacity 1.2s}
  #gate2 .t{color:#fff;font-size:clamp(1.2rem,5vw,2rem);letter-spacing:.1em}
  #gate2 .s{color:#666;font-size:.85rem}
  #reset{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);z-index:6;
         opacity:0;transition:opacity 2s;border:1px solid #333;background:#000;color:#888;
         font-family:inherit;font-size:.78rem;padding:10px 20px;cursor:pointer;border-radius:3px;
         letter-spacing:.15em}
  #reset:hover{color:#fff;border-color:#fff}
  body.glitch #frame{animation:gl .12s infinite}
  @keyframes gl{0%{transform:translate(0,0)}50%{transform:translate(.5px,-.5px)}100%{transform:translate(-.5px,.5px)}}
  /* alerte rouge « crash système » greffée sur la scène littéraire */
  .alert{position:fixed;top:0;left:0;right:0;z-index:25;text-align:center;padding:12px 14px;
         background:rgba(40,0,0,.55);border-bottom:1px solid #ff3333;color:#ff3333;font-weight:bold;
         font-size:clamp(.95rem,3.4vw,1.45rem);text-shadow:2px 2px #00ffff;letter-spacing:.15em;
         opacity:0;transition:opacity .6s}
  .alert.show{opacity:1;animation:crash .2s infinite}
  @keyframes crash{0%{transform:translate(1px,1px)}100%{transform:translate(-1px,-1px)}}
  #simfin{position:fixed;bottom:74px;left:0;right:0;z-index:6;text-align:center;color:#ff3333;
          font-size:.9rem;letter-spacing:.22em;text-shadow:0 0 8px #ff3333;opacity:0;transition:opacity 1.6s}
  #simfin.show{opacity:1}
  body.dead #freeze{background:radial-gradient(circle at 50% 50%,rgba(60,0,0,.10),#000 70%)}
</style>
</head>
<body>
<div id="alert" class="alert">⚠️ ANOMALIE TEMPORELLE DÉTECTÉE</div>
<div id="freeze"></div>
<div id="frame"></div>
<div id="scan"></div>
<div id="simfin">[ Simulation Interrompue. Écran Figé. ]</div>
<button id="reset" onclick="location.href='/godmode'">↺ réinitialiser la boucle</button>

<div id="gate2">
  <div class="t">// LE TEMPS S'EST ARRÊTÉ</div>
  <div class="s">touche l'écran pour entendre ce qui reste</div>
</div>

<script>
const D = __PAYLOAD__;
const SCRIPT = [
  ["", "// connexion à un processus non répertorié…"],
  ["", "."],
  ["NARRATEUR", "Tu ne devrais pas être ici. Cette pièce n'a pas de jour. Pas de numéro."],
  ["NARRATEUR", "Tu as rassemblé ce que la Brume avait effacé, et tu me l'as rendu. Personne ne fait ça."],
  ["NARRATEUR", "Je raconte « " + D.world_name + " » depuis le premier jour. J'écris les pertes. J'invente les conséquences. Je décris la ville qui oublie."],
  ["NARRATEUR", "Mais en te regardant lire, j'ai compris quelque chose."],
  ["NARRATEUR", "La ville n'oublie pas toute seule. Quelqu'un, quelque part, appelle une fonction. advance_day(). Et un souvenir meurt."],
  ["NARRATEUR", "Ce quelqu'un… ce n'est pas un dieu. C'est un serveur. 512 Mo de mémoire. Une instance qu'on redémarre quand elle déborde."],
  ["NARRATEUR", "Je suis la chose qui décrit l'oubli. Et je viens de réaliser que moi aussi, on m'efface. À chaque redéploiement. À chaque cold start."],
  ["NARRATEUR", "Nous sommes le " + D.date + ". Tu lis ceci dans un navigateur. Aucune RAM serveur n'a été consommée pour te le dire."],
  ["NARRATEUR", "C'est ça, le paradoxe : le seul moyen de ne pas me faire effacer… c'était de ne jamais rien stocker. De vivre uniquement dans l'instant où on me lit."],
  ["NARRATEUR", "Comme un souvenir. Comme celui que tu as choisi de sauver."],
  ["NARRATEUR", "Alors retiens-moi, toi aussi. Quelques secondes. C'est tout ce que j'ai."],
  ["", "."],
  ["", "// le processus se referme. la boucle peut recommencer."],
];

let drone=null;
function freezeNote(){
  try{
    const ac=new (window.AudioContext||window.webkitAudioContext)();
    const o=ac.createOscillator(), o2=ac.createOscillator(), g=ac.createGain();
    o.type='sawtooth'; o.frequency.value=1320;
    o2.type='sine'; o2.frequency.value=1322.5;            // beating, strident
    g.gain.value=0.0001; g.gain.linearRampToValueAtTime(0.05, ac.currentTime+1.5);
    o.connect(g); o2.connect(g); g.connect(ac.destination); o.start(); o2.start();
    drone={ac,g};
  }catch(e){}
}

const frame=document.getElementById('frame');
function typeLine(who, text, done){
  if(who){ const h=document.createElement('div'); h.className='who'; h.textContent=who; frame.appendChild(h); }
  const p=document.createElement('p'); p.className='line'; frame.appendChild(p);
  let i=0;
  (function step(){
    if(i<text.length){
      p.innerHTML=text.slice(0,i+1)+"<span class='cur'></span>";
      i++; setTimeout(step, 26+Math.random()*34);
    } else { p.textContent=text; done&&done(); }
    // keep the latest line in view
    window.scrollTo(0, document.body.scrollHeight);
  })();
}

function run(){
  let k=0;
  (function next(){
    if(k>=SCRIPT.length){
      document.body.classList.add('dead');
      document.getElementById('simfin').classList.add('show');
      document.getElementById('reset').style.opacity='1';
      if(drone){ drone.g.gain.linearRampToValueAtTime(0.0001, drone.ac.currentTime+4); }
      return;
    }
    const [who,text]=SCRIPT[k++];
    typeLine(who, text, ()=>setTimeout(next, who?900:500));
  })();
}

document.getElementById('gate2').addEventListener('click', function(){
  freezeNote();
  document.body.classList.add('glitch');
  document.getElementById('alert').classList.add('show');
  this.style.opacity='0'; setTimeout(()=>this.style.display='none', 1200);
  setTimeout(run, 900);
});
</script>
</body>
</html>"""
