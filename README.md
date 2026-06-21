# Crea — AI Video Agent

Backend API for AI-powered short-form video generation (TikTok / YouTube Shorts / Reels).

## What it does

- Generates a viral script (hook → body → conclusion) for a given topic
- Splits the script into timestamped scenes with visual keyword suggestions
- Produces SEO data: titles, description, hashtags

## Stack

- **Python 3.12**
- **FastAPI** + **Uvicorn**
- **Pydantic v2**
- Deployable on **Render** (free tier)

## Project structure

```
app/
├── main.py              # FastAPI entry point
├── core/
│   ├── config.py        # settings (env vars)
│   └── prompts.py       # prompt templates
├── models/
│   └── schemas.py       # Pydantic schemas
├── services/
│   ├── script.py        # script generation
│   ├── scenes.py        # scene splitting
│   ├── seo.py           # titles / hashtags
│   └── video_plan.py    # final video plan builder
└── utils/
    └── helpers.py
output/                  # generated video output (future)
requirements.txt
render.yaml              # Render deployment config
```

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the interactive API docs.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Status check |
| GET | `/health` | Health probe |
| POST | `/generate` | Full video plan |
| POST | `/hooks` | Hook variants only |
| POST | `/seo` | Titles + hashtags only |

### Example request

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "argent sur internet", "language": "fr", "style": "viral"}'
```

### Example response (truncated)

```json
{
  "topic": "argent sur internet",
  "language": "fr",
  "style": "viral",
  "script": {
    "hook": "Personne ne te dit ça sur argent sur internet...",
    "body": ["..."],
    "conclusion": "Maintenant tu connais la vérité. Abonne-toi pour la suite."
  },
  "scenes": [
    { "index": 1, "text": "...", "visual_keywords": ["..."], "duration_hint": "3s" }
  ],
  "seo": {
    "titles": ["..."],
    "description": "...",
    "hashtags": ["#fyp", "#viral", "..."]
  },
  "format": "9:16 vertical",
  "estimated_duration": "0m37s",
  "status": "ready_for_rendering"
}
```

## Deploy to Render

1. Push this repo to GitHub
2. Create a **New Web Service** on [render.com](https://render.com)
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — click **Deploy**
5. Your API is live at `https://<your-service>.onrender.com`

## Roadmap

- [ ] Pexels API integration — auto-fetch stock clips per scene
- [ ] MoviePy / FFmpeg assembly — generate a real MP4
- [ ] TTS voice-over (gTTS / ElevenLabs)
- [ ] Claude API integration for higher-quality scripts
- [ ] Job queue (Celery / Redis) for async video rendering
