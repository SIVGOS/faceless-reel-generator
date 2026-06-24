# CLAUDE.md — Faceless Reel Generator

Containerized multiplayer web app that turns a text prompt into a 9:16 vertical
video reel: Gemini writes a script → `edge-tts` narrates it → `faster-whisper`
aligns words → an `.ass` karaoke caption file is built → FFmpeg burns captions
over a random background loop and encodes to h264/aac.

## Tech stack
- **Backend:** FastAPI (Python 3.11+ in Docker), Uvicorn.
- **DB:** SQLite via SQLAlchemy 2.x ORM. File lives at `data/app.db`.
- **Auth:** `passlib[bcrypt]` password hashing + JWT in an HTTP-only cookie.
- **AI text:** `google-genai` SDK, model `gemini-2.5-flash`.
- **Media:** native `ffmpeg` (Docker), `edge-tts` (voice), `faster-whisper`
  (`base` model, `compute_type="int8"`, CPU) for word-level timestamps.
- **Frontend:** vanilla HTML/CSS/JS (native `fetch`), single dark-themed page.

## Layout
```
app/
  main.py            FastAPI app, static mount, router wiring
  config.py          env-driven settings (pydantic-settings)
  database.py        SQLAlchemy engine + session dependency
  models.py          User, Project ORM models
  schemas.py         Pydantic request/response models
  auth.py            hashing, JWT encode/decode, current-user dependency
  routers/
    auth.py          /api/auth/register, /login, /logout, /me
    projects.py      /api/projects CRUD + /generate-script + /compile
  services/
    gemini.py        script generation (lazy SDK import)
    tts.py           edge-tts narration (lazy import)
    transcribe.py    faster-whisper word timestamps (lazy import)
    subtitles.py     PURE python .ass karaoke builder (no heavy deps)
    compose.py       ffmpeg subprocess assembly
  static/            index.html, style.css, app.js
backgrounds/         mounted volume of source .mp4 loops (not baked in image)
data/                sqlite db + generated audio/video (gitignored)
tests/               offline sanity tests (subtitles, ffmpeg arg builder)
```

## Development patterns (IMPORTANT)
- **Lazy heavy imports.** `google-genai`, `edge-tts`, `faster-whisper` are
  imported *inside* functions, never at module top. This keeps `subtitles.py`,
  `compose.py` arg-building, and the API layer importable and unit-testable
  without GPU/network/model downloads.
- **Subprocess safety.** All FFmpeg/whisper work is built as an explicit
  `list[str]` argv (never `shell=True`), runs with a timeout, and writes to
  per-project temp paths under `data/projects/<project_id>/`. Always check
  `returncode` and surface `stderr`; never leak a blocking process.
- **Tenancy.** Every project query is scoped by `user_id` from the JWT. A user
  can only read/run/delete their own projects — enforced in the router, not the
  client.
- **Pure helpers stay pure.** `subtitles.py` takes plain word/timestamp dicts
  and returns a string; it does no I/O beyond an optional file write. This is
  the layer covered by sanity assertions against mock data.

## Commands
- Run locally (needs deps): `uvicorn app.main:app --reload`
- Run via Docker: `docker compose up --build`
- Tests / sanity checks: `python -m pytest tests/ -q`
- Syntax check everything: `python -m compileall app`

## Env (.env, see .env.example)
- `GEMINI_API_KEY` — Google AI Studio key.
- `JWT_SECRET` — random secret for signing session tokens.
- `TTS_VOICE` — default `en-US-ChristopherNeural`.
- `WHISPER_MODEL` — default `base`.

## Git
Work proceeds in checkpoints: scaffold → schema → pipeline → auth → frontend →
docker. Commit at each green checkpoint.
