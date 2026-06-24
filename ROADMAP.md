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
- **Caption engine:** a real keyframe animation engine (Remotion recommended;
  MoviePy is the lighter, license-clean, pure-Python alternative). **Final
  Remotion-vs-MoviePy pick is still open** — see "Open decisions" below.

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
prompt
  └─▶ Gemini script  (+ optional emphasis keywords)
        └─▶ Gemini TTS (director-style prompt) ─▶ 24kHz PCM ─▶ wav/mp3 + loudnorm
              └─▶ faster-whisper ─▶ word timestamps
                    └─▶ caption timeline JSON  (word groups + timings + emphasis)
                          └─▶ render engine (bg + Ken Burns + gradient overlay
                              + animated word-pop captions + audio) ─▶ reel.mp4
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
- **Remotion path:** a `remotion/` Node project with `ReelComposition.tsx`
  parameterized by `audioSrc`, `backgroundSrc`, `words`, `style`, `emphasisWords`.
  Captions: per-word **spring scale-in**, active word **highlight (accent color +
  scale + rounded pill)**, past words dim, heavy bundled font (Montserrat
  ExtraBold / Anton), lower/upper-third position.
  `app/services/remotion.py` builds the Node render argv and runs it as a
  **subprocess with timeout + stderr surfacing** (same safety boundary as
  `compose.py`); props passed via a JSON file, not argv.
- **MoviePy path (alternative):** keep everything in Python; animate text clips
  via per-frame functions; composite over background.
- Keep the ASS builder as a fast/lightweight fallback (`CAPTION_ENGINE=ass`).

### 4. Video polish — fixes #4
- Ken Burns zoom/pan on background; gradient/vignette overlay behind captions.
- Encode h264 high profile at `crf ~18` (vs current `veryfast`/`crf 23`).
- Optional `MUSIC_FOLDER_PATH` (mirrors `BG_VIDEO_FOLDER_PATH`) with sidechain
  ducking under narration.
- Provide higher-res 1080×1920 source clips (quality in = quality out).

## Planned config (env)
| Var | Purpose |
|---|---|
| `TTS_PROVIDER` | `gemini` \| `edge` |
| `TTS_GEMINI_MODEL` | default `gemini-3.1-flash-tts-preview` |
| `TTS_GEMINI_VOICE` | e.g. `Kore`, `Puck`, `Zephyr` |
| `TTS_STYLE_PROMPT` | director-style narration instruction |
| `CAPTION_ENGINE` | `remotion` \| `moviepy` \| `ass` |
| `RENDER_TIMEOUT_SECONDS` | cap for the render subprocess |
| `MUSIC_FOLDER_PATH` | optional background-music pool |

## Docker impact
- If Remotion: multi-stage add **Node + headless Chromium** (image +300–500 MB,
  needs `libnss3`/font deps + `--no-sandbox`).
- Bundle display fonts regardless of engine.

## Risks
- Image size + build time jump (Chromium) if Remotion.
- Per-video render time climbs → async + concurrency limits required.
- **Remotion licensing**: free for individuals/small companies; paid Company
  License above a size threshold — verify for the `SIVGOS` org before committing.
- Preview TTS model (`*-preview`) IDs/behavior may change; pin and re-verify.

## Open decisions (need user input before coding)
1. **Remotion vs MoviePy** — fidelity + heavier image (+ licensing) vs
   pure-Python + lighter + MIT.
2. Background music: yes/no for v2.

## User action items
See `ACTION_ITEMS.md`.

---

### Verified facts (as of 2026-06-24)
- Gemini TTS uses the standard `google-genai` SDK + AI Studio API key — **no new
  API to enable, no service account.**
- `gemini-3.1-flash-tts-preview`: **free tier available**; paid ≈ **$20 / 1M audio
  output tokens**.
- `gemini-2.5-flash-preview-tts`: free tier available; paid ≈ $10 / 1M.
- `gemini-2.5-pro-preview-tts`: **no free tier** — requires billing.
- Enabling billing on a Gemini project removes the free tier for that project
  (every call becomes billable). Rate limits are per Google Cloud project.

Sources:
- https://ai.google.dev/gemini-api/docs/speech-generation
- https://ai.google.dev/gemini-api/docs/pricing
- https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
