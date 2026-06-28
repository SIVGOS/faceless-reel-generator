# CLAUDE.md — Faceless Reel Generator

Containerized multiplayer web app that turns a text prompt into a 9:16 vertical
video reel: Gemini writes a script → Gemini native TTS (or `edge-tts`) narrates
it → `faster-whisper` produces word timings → captions are rendered (animated
MoviePy word-pop, or `.ass` fallback) over a background loop and encoded to
h264/aac.

**Languages:** English plus **Hindi & Sanskrit** (written in Devanagari). A
language picker (auto/english/hindi/sanskrit) drives generation; any script
containing Devanagari automatically gets an Indian-accent TTS director prompt,
the larger whisper model + a Hindi alignment hint, and a per-word Devanagari
caption font. Captions always show the EXACT script text — whisper provides only
timing (its text is discarded), so spellings are never corrupted (see
`services/align.py`).

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
    gemini.py        script generation + per-language directive (lazy SDK import)
    tts.py           Gemini|edge narration; Indian style/voice on Devanagari (lazy)
    transcribe.py    faster-whisper word timings; per-model cache + lang hint
    language.py      PURE Devanagari detection + generation-language constants
    align.py         PURE remap of whisper timings onto the KNOWN script text
    captions.py      PURE engine-agnostic caption timeline (JSON) builder
    captions_moviepy.py  MoviePy animated captions; per-word Latin/Devanagari font
    subtitles.py     PURE python .ass karaoke builder (no heavy deps)
    compose.py       ffmpeg subprocess assembly (ass engine + background picker)
  assets/fonts/      bundled OFL fonts: Anton (Latin) + NotoSansDevanagari (ships
                     via COPY app; Pillow's bundled raqm shapes Devanagari)
  static/            index.html (incl. language picker), style.css, app.js
backgrounds/         local fallback pool (BG_VIDEO_FOLDER_PATH overrides; media
                     lives outside the repo, mounted read-only in Docker)
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
- **Pure helpers stay pure.** `subtitles.py`, `captions.py`, `language.py`, and
  `align.py` take plain dicts/strings and return data with no heavy deps or I/O
  (beyond an optional file write). This is the layer covered by sanity assertions
  against mock data — keep new logic here testable without GPU/network/model.
- **Captions show the script, not the transcription.** whisper is used ONLY for
  word *timing*; its *text* is discarded. `align.py` remaps those timings onto the
  known-correct script via a monotonic alignment (consonant-skeleton matching for
  Devanagari), so caption spelling can never be corrupted by ASR errors. Always
  run new caption work through this remap, not raw whisper text.

## Commands
- Run locally (needs deps): `uvicorn app.main:app --reload`
- Run via Docker: `docker compose up --build`
- Tests / sanity checks: `python -m pytest tests/ -q`
- Syntax check everything: `python -m compileall app`

## Local dev environment — Apple Silicon Docker (IMPORTANT)
Before ANY local Docker work (`docker build`, `docker compose`, render benchmark),
run **`./scripts/dev-docker.sh`** first. On this Apple-Silicon machine the default
Colima profile is EMULATED x86_64, which makes the MoviePy render unusably slow
(a 53s reel never finished in 30+ min); the native arm64 profile renders it in
~150s. The script stops any running emulated-x86 Colima profile and brings up (or
reuses) the native arm64 profile (`arm`, 4 cpu / 8 GiB), then switches the docker
context to `colima-arm`. It is idempotent and does NOT delete the x86 `default`
profile (it holds other projects' containers). No-op / errors out cleanly on
native-Linux hosts (incl. the deploy server) — there, use docker directly.
NOTE: native arm64 is an OPTIMISTIC perf proxy; the budget x86 deploy box (4 vCPU)
will be slower — confirm production render timing on the real server.

## Env (.env, see .env.example)
- `GEMINI_API_KEY` — Google AI Studio key.
- `GEMINI_GENERATION_MODEL` / `GEMINI_EMBEDDING_MODEL` — Gemini model ids.
- `JWT_SECRET` — random secret for signing session tokens.
- `TTS_VOICE` — edge fallback voice, default `en-US-ChristopherNeural`.
- `WHISPER_MODEL` — default `base`.
- `WHISPER_MODEL_DEVANAGARI` — model auto-used when the script has Devanagari,
  default `small` (better Devanagari TIMING; text comes from the script regardless).
- `TTS_PROVIDER` / `TTS_GEMINI_*` / `TTS_FALLBACK_TO_EDGE` — Gemini TTS config.
- `TTS_VOICE_INDIAN` (`hi-IN-MadhurNeural`) / `TTS_STYLE_PROMPT_INDIAN` — auto-used
  for Devanagari content (authentic pronunciation + neutral Indian English accent).
- `CAPTION_ENGINE` / `CAPTION_FONT_PATH` / `CAPTION_FONT_DEVANAGARI_PATH` / `CAPTION_FPS`.
- `BG_VIDEO_FOLDER_PATH` — path to the external `.mp4` background library
  (maps to `settings.backgrounds_dir`; defaults to `./backgrounds`).
- `MUSIC_FOLDER_PATH` — external `.mp3` pool (defaults to `./music`; checkpoint F).

## Git
Work proceeds in checkpoints: scaffold → schema → pipeline → auth → frontend →
docker. Commit at each green checkpoint.

## Roadmap — v2 (in progress)
Quality/polish pass. Full detail in `ROADMAP.md`, sequenced build in
`BUILD_PLAN.md`, user prerequisites in `ACTION_ITEMS.md`.

**Built & on `main`:**
- **Async rendering** (checkpoint B) — background job + status polling.
- **Voice** (checkpoint C) — **Gemini native TTS** (`google-genai` + existing
  `GEMINI_API_KEY`), 24 kHz PCM → WAV + ffmpeg `loudnorm`; edge-tts fallback.
- **Captions** (checkpoint D) — word-by-word pop/scale/highlight via **MoviePy**;
  pure `captions.py` emits engine-agnostic timeline JSON; ASS stays as
  `CAPTION_ENGINE=ass`. Remotion documented fallback (not built).
- **Hindi & Sanskrit (Devanagari)** — language picker drives generation;
  Devanagari auto-detected → Indian-accent TTS, larger whisper model + `hi` hint,
  per-word Noto Devanagari font. **Captions remap whisper timings onto the exact
  script (`align.py`)** so spelling is never ASR-corrupted.

**Not yet built:** Video polish (Ken Burns + gradient + h264 `crf ~18`),
Music + user asset selection (`MUSIC_FOLDER_PATH`, `GET /api/assets/*`,
whitelisted, ducked via `sidechaincompress`), admin user mgmt, responsive UI,
docker env-var pass-through gap, backup/restore. See `BUILD_PLAN.md` (E→J).
