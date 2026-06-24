# Roadmap — Reel Forge v2 (Quality & Polish)

Status: **planned, not yet implemented** (building in upcoming sessions).
This captures the agreed direction so any session can pick it up.

## Goals (from user feedback on v1 output)
1. Voice sounds mechanical.
2. Non-English words are mispronounced.
3. Captions just slide left→right (ASS `\k` highlight sweep) — want a polished,
   professional animation.
4. Video looks soft/flat.

## Locked decisions
- **Voice engine:** **Gemini native TTS** (`gemini-3.1-flash-tts-preview`),
  reusing the existing `google-genai` SDK and the existing AI Studio
  `GEMINI_API_KEY`. Keep `edge-tts` as the free fallback provider.
- **Caption engine:** **MoviePy** (pure-Python, MIT-licensed, lighter image) —
  chosen to minimize cost (no Remotion license exposure, no Node/Chromium in the
  image). **Remotion is the documented fallback** if MoviePy's fidelity proves
  unsatisfying; the timeline JSON contract (below) is engine-agnostic so swapping
  later touches only the render stage.

## Why Gemini TTS
- Same SDK + same API key already in use — no new account/credential.
- 30 voices, 100+ languages with auto language detection (helps #2).
- Expressivity via **natural-language director prompts** + inline audio tags
  (`[slow]`, `[whispers]`, `[excited]`) — the lever against the mechanical feel.
- Output is **24 kHz PCM, base64** (not mp3) → pipeline must decode to WAV.
- **Caveat:** no SSML / phoneme-level control. Tricky proper nouns will be much
  better but not *guaranteed* precise. The only precise fix is **Google Cloud
  TTS (Neural2/Studio) + `<phoneme>` SSML**, which needs separate GCP setup —
  kept as an escape hatch, not the default.

## Target render flow
```
prompt  + user-selected background video  + user-selected music (or none)
  └─▶ Gemini script  (+ optional emphasis keywords)
        └─▶ Gemini TTS (director-style prompt) ─▶ 24kHz PCM ─▶ wav/mp3 + loudnorm
              └─▶ faster-whisper ─▶ word timestamps
                    └─▶ caption timeline JSON  (word groups + timings + emphasis)
                          └─▶ render engine (chosen bg + Ken Burns + gradient
                              overlay + animated word-pop captions + narration
                              mixed over ducked music) ─▶ reel.mp4
```

## Work breakdown

### 1. Voice — fixes #1 + #2  *(contained, ship first)*
- `app/services/tts.py`: provider interface; `gemini` provider via `google-genai`
  with a configurable **style prompt** + audio tags.
- Decode base64 24 kHz PCM → WAV (faster-whisper reads WAV directly); mux mp3 for
  the final.
- Add ffmpeg `loudnorm` (EBU R128) for consistent loudness.

### 2. Async rendering — prerequisite for slow renders
- v2 renders (Gemini TTS + whisper + animation engine) exceed a safe request
  timeout. Move `render_reel` to a **background job**; reuse the existing
  `projects.status` field (`pending/rendering/done/failed`).
- Frontend: poll `/api/projects` while anything is `rendering` (status badges
  already exist in the gallery).
- Start with FastAPI `BackgroundTasks`; graduate to a real queue (arq/RQ + Redis)
  only if concurrent multiplayer load demands it.

### 3. Caption animation — fixes #3  *(headline visual upgrade)*
- `app/services/captions.py` (new, **pure & unit-testable** like today's
  `subtitles.py`): group whisper words into 1–3-word on-screen chunks; attach
  active timing + `emphasis` flags (emphasis can come from Gemini keywords).
  Emits the timeline **JSON** contract.
- **MoviePy path (chosen):** stays pure-Python in the existing pipeline.
  `app/services/captions_moviepy.py` reads the timeline JSON and builds the
  animated caption layer — per-word **pop / scale-in** and active-word
  **highlight (accent color + scale)** via custom easing functions of time `t`,
  composited over the background. Heavy bundled font (Montserrat ExtraBold /
  Anton), lower/upper-third position. Renders via ffmpeg under the hood;
  invoked behind the same render-job boundary (timeout + error surfacing).
- **Remotion path (documented fallback, not built):** if MoviePy fidelity is
  unsatisfying, a `remotion/` Node project with `ReelComposition.tsx` (spring
  physics, rounded highlight pill) consuming the *same* timeline JSON. Adds
  Node + Chromium and a license check — see Risks. Deferred unless needed.
- Keep the ASS builder as a fast/lightweight fallback (`CAPTION_ENGINE=ass`).

### 4. Video polish — fixes #4
- Ken Burns zoom/pan on background; gradient/vignette overlay behind captions.
- Encode h264 high profile at `crf ~18` (vs current `veryfast`/`crf 23`).
- Provide higher-res 1080×1920 source clips (quality in = quality out).

### 5. Background music + user asset selection  *(confirmed feature)*
- **Music library:** `MUSIC_FOLDER_PATH` env, a folder of `.mp3` clips mirroring
  `BG_VIDEO_FOLDER_PATH` exactly — kept outside the repo, mounted **read-only**
  into the container at a fixed path, refreshable without a rebuild.
- **Audio mix:** narration is the foreground; selected music is **ducked under
  it** (ffmpeg `sidechaincompress`), looped/trimmed to the reel length, with
  fade in/out, then `loudnorm` on the final mix. **"No music"** is a first-class
  option (skip the music input → narration only).
- **User selection in the web app (NEW — replaces pure-random):**
  - `GET /api/assets/backgrounds` and `GET /api/assets/music` list the available
    files in each pool (filenames + maybe a thumbnail/preview later).
  - The compile request accepts an optional chosen `background` and `music`
    (filename) plus an explicit `music: none`. If background is omitted, fall
    back to today's **random** pick; music defaults to none unless chosen.
  - **Security (public, multi-tenant app):** treat selections as a **whitelist**
    — resolve only against the listed pool by exact basename, reject anything
    that escapes the folder (no path traversal), before it ever reaches the
    ffmpeg argv. Mirrors the existing `pick_background` safety.
  - Frontend: add **background** and **music** pickers (dropdown/grid, with a
    "No music" choice) to the workspace controls; optional inline preview.
  - Persist the chosen `background`/`music` on the `projects` row for reproducible
    re-renders and gallery display.

## Planned config (env)
| Var | Purpose |
|---|---|
| `TTS_PROVIDER` | `gemini` \| `edge` |
| `TTS_GEMINI_MODEL` | default `gemini-3.1-flash-tts-preview` |
| `TTS_GEMINI_VOICE` | e.g. `Kore`, `Puck`, `Zephyr` |
| `TTS_STYLE_PROMPT` | director-style narration instruction |
| `CAPTION_ENGINE` | default `moviepy`; `ass` (light fallback), `remotion` (future) |
| `RENDER_TIMEOUT_SECONDS` | cap for the render subprocess |
| `MUSIC_FOLDER_PATH` | background-music `.mp3` pool (mirrors `BG_VIDEO_FOLDER_PATH`) |

## Schema / API additions
- `projects`: add `background` and `music` columns (chosen basenames; `music`
  nullable = no music) for reproducible re-renders + gallery display.
- New: `GET /api/assets/backgrounds`, `GET /api/assets/music` (list pools).
- Compile/generate request gains optional `background` + `music` selections
  (whitelisted against the pools).

## Docker impact
- MoviePy: add the Python package + its ffmpeg/PIL needs — modest. No Node,
  no Chromium.
- Mount `MUSIC_FOLDER_PATH` read-only (mirrors the backgrounds mount), defaulting
  to `./music` when unset.
- Bundle display fonts (Montserrat ExtraBold / Anton) for captions.
- (Only if we ever switch to Remotion: +Node +headless Chromium, ~300–500 MB,
  `libnss3`/font deps + `--no-sandbox`.)

## Risks
- Per-video render time climbs → async + concurrency limits required.
- MoviePy animation is hand-rolled (easing functions) and tops out below
  Remotion's effortless polish; per-frame Python compositing at 1080×1920 can be
  slow — watch render time and cap concurrency.
- Preview TTS model (`*-preview`) IDs/behavior may change; pin and re-verify.
- (Deferred) If MoviePy fidelity disappoints → Remotion, which carries a Company
  License check (free only for individuals / for-profits ≤3 people) and a heavier
  image. Same timeline JSON, so the swap is contained.

## Open decisions
None — direction is fully settled. Ready to draft a step-by-step build plan.

## User action items
See `ACTION_ITEMS.md`.

---

### Verified facts (as of 2026-06-24)
- **The project's `GEMINI_API_KEY` is already on the paid tier** (free quota used
  up). So all Gemini TTS models are available — including the paid-only
  `gemini-2.5-pro-preview-tts` — with no extra setup, and no separate key needed.
- Gemini TTS uses the standard `google-genai` SDK + the same API key — **no new
  API to enable, no service account.**
- Pricing (paid): `gemini-3.1-flash-tts-preview` ≈ **$20 / 1M audio output
  tokens**; `gemini-2.5-flash-preview-tts` ≈ $10 / 1M; `gemini-2.5-pro-preview-tts`
  ≈ $20 / 1M. Default = 3.1-flash-tts (newest, best control); 2.5-pro is a quality
  A/B option now that billing is on.
- Rate limits are per Google Cloud project.

Sources:
- https://ai.google.dev/gemini-api/docs/speech-generation
- https://ai.google.dev/gemini-api/docs/pricing
- https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
