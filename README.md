# Reel Forge — Faceless Reel Generator

A containerized, multiplayer web app that turns a single text prompt into a
9:16 vertical video reel. Gemini writes the script, `edge-tts` narrates it,
`faster-whisper` aligns the words, a karaoke `.ass` caption file is generated,
and FFmpeg burns the captions over a random background loop — encoded to compact
h264/aac.

## Pipeline

```
prompt ──▶ Gemini (gemini-2.5-flash) ──▶ script
script ──▶ edge-tts ──▶ narration.mp3
narration.mp3 ──▶ faster-whisper (int8, CPU) ──▶ word timestamps
word timestamps ──▶ .ass karaoke captions
captions + narration + random ./backgrounds/*.mp4 ──▶ ffmpeg ──▶ reel.mp4
```

## Quick start (Docker)

1. Add at least one vertical `.mp4` to `./backgrounds/` (mounted as a volume, so
   you can refresh the pool without rebuilding the image).
2. Copy env and set your key:
   ```bash
   cp .env.example .env
   # set GEMINI_API_KEY and a random JWT_SECRET
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
3. Build and run:
   ```bash
   docker compose up --build      # or: docker-compose up --build
   ```
4. Open http://localhost:8000 — register, generate a script, compile.

## Local dev (no Docker)

Requires Python 3.11+ and a system `ffmpeg` on PATH.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY
uvicorn app.main:app --reload
```

## Tests / verification

```bash
python -m pytest tests/ -q      # 18 offline tests: subtitles, ffmpeg argv, auth, tenancy
python -m compileall app        # syntax check
```

The media tests are fully offline — Gemini, edge-tts, and faster-whisper are
lazy-imported and the render pipeline is mocked, so no network or model
downloads are needed to verify the core logic.

## API surface

| Method | Path                              | Notes                          |
|--------|-----------------------------------|--------------------------------|
| POST   | `/api/auth/register`              | sets HTTP-only session cookie  |
| POST   | `/api/auth/login`                 | sets HTTP-only session cookie  |
| POST   | `/api/auth/logout`                | clears cookie                  |
| GET    | `/api/auth/me`                    | current user                   |
| GET    | `/api/projects`                   | own projects only              |
| POST   | `/api/projects/generate-script`   | Gemini → script + project      |
| PUT    | `/api/projects/{id}/script`       | persist edited script          |
| POST   | `/api/projects/{id}/compile`      | run render chain               |
| GET    | `/api/projects/{id}/video`        | stream/download own reel       |
| DELETE | `/api/projects/{id}`              | delete own project             |

Every project route is scoped to the authenticated user — cross-tenant access
returns 404.

See `CLAUDE.md` for development patterns and architecture details.
