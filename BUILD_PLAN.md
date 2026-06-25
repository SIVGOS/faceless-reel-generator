# Build Plan — Reel Forge v2

Execution plan for the v2 direction locked in `ROADMAP.md`. This is the
*in-what-order / which-files / which-commit* layer; `ROADMAP.md` holds the
*what & why*, `ACTION_ITEMS.md` holds user prerequisites.

**Sequencing decision (2026-06-25):** *quality first*. Ship the four quality
fixes, then the release gate. The release gate (Checkpoint G) is still a **hard
blocker before any public/multi-user deployment** — do not expose the app to real
users until G has landed.

Each checkpoint is independently shippable and ends at a green commit, matching
the repo's "commit at each green checkpoint" rule. Pure helpers stay pure and
unit-tested (the `subtitles.py` discipline); heavy deps stay lazily imported.

---

## Checkpoint 0 — TTS capability check  *(no code, ~5 min)*
The only user-side open item. Verify the existing `GEMINI_API_KEY` can call the
chosen TTS model in this region before building on it.
- In-session script: call `gemini-3.1-flash-tts-preview` (and optionally
  `gemini-2.5-pro-preview-tts`) with a one-line prompt; confirm 24 kHz PCM comes
  back and decodes.
- **Exit criteria:** a playable WAV from each model we plan to support.
- If the preview model is unavailable in-region → fall back to
  `gemini-2.5-flash-preview-tts`; edge-tts remains the free fallback regardless.

---

## Checkpoint A — Foundation: config + one-pass schema migration
Do **all** schema changes in a single SQLite rebuild to avoid repeated
`ALTER TABLE` churn. Nothing user-facing changes yet; auth must still work.
- `app/config.py` + `.env.example`: add `tts_provider`, `tts_gemini_model`,
  `tts_gemini_voice`, `tts_style_prompt`, `caption_engine`,
  `render_timeout_seconds`, `music_folder_path` (alias `MUSIC_FOLDER_PATH`,
  default `./music`, **never auto-created** — mirror the backgrounds treatment),
  `admin_email`. Add `music_dir` property mirroring `backgrounds_dir`.
- `app/models.py`:
  - `User`: rename `username` → `email` (unique, indexed, lowercased); add
    `is_admin: bool` (default `False`).
  - `Project`: add `background: str | None`, `music: str | None` (chosen
    basenames; `music` null = no music).
- `app/database.py`: add a small **idempotent migration** on startup (inspect
  `PRAGMA table_info`; rename/rebuild `users` and add columns if absent). SQLite
  can't drop/rename columns pre-3.25 cleanly → use the create-new-table +
  copy + swap pattern; guard so it's a no-op on already-migrated DBs.
- `app/schemas.py`: `UserCreate`/`UserOut` key on `email` (EmailStr); `ProjectOut`
  exposes `background`/`music`.
- `app/auth.py` + `app/routers/auth.py`: `login` and `get_current_user` look up
  by `email`. (Closing signup happens in G; here we only make email the key.)
- **Tests:** migration is idempotent (run twice on a temp DB); login works by
  email. **Commit:** `v2: config + email/admin/asset schema migration`.

---

## Checkpoint B — Async rendering  *(prerequisite for slow v2 renders)*
v2 renders exceed a safe request timeout, so move rendering off the request path
*before* adding the slow stages.
- `app/routers/projects.py`: `/{id}/compile` flips status to `rendering`,
  schedules the render via FastAPI `BackgroundTasks`, returns `202` immediately.
  Reuse the existing `status` field (`scripted→rendering→done/failed`) and
  `error` column. Each job opens its **own DB session** (don't reuse the
  request's).
- `pipeline.render_reel` already isolates per-project temp dirs — keep as the job
  body; wrap so any service error sets `failed` + `error`.
- Frontend: gallery already has status badges → poll `/api/projects` while
  anything is `rendering`.
- Honor `render_timeout_seconds` (thread through to the ffmpeg/whisper steps).
- Graduate to arq/RQ + Redis only if concurrent load demands it (noted, not now).
- **Tests:** compile returns 202 + sets `rendering`; failing job records `failed`.
  **Commit:** `v2: async render job + status polling`.

---

## Checkpoint C — Voice: Gemini TTS  *(fixes #1 mechanical, #2 mispronunciation)*
Smallest high-value quality win; build behind the async boundary from B.
- `app/services/tts.py`: introduce a provider seam.
  - Keep `synthesize(...)` as the public entry; dispatch on
    `settings.tts_provider` (`gemini` | `edge`).
  - `edge` path = current code (free fallback).
  - `gemini` path: lazy-import `google-genai`; send script + `tts_style_prompt`
    (director-style) + inline audio tags; receive **base64 24 kHz PCM**; decode
    to WAV (faster-whisper reads WAV directly), then ffmpeg `loudnorm` (EBU R128),
    mux mp3 for the final. Raise `TTSError` on any failure → auto-fallback to edge
    is configurable.
- `app/services/pipeline.py`: narration step is provider-agnostic (already calls
  `tts.synthesize`); ensure it passes a WAV path the transcriber accepts.
- **Tests:** provider dispatch picks the right backend; PCM→WAV decode on a
  fixture buffer; loudnorm arg builder is pure + asserted. (No network in tests —
  mock the SDK.) **Commit:** `v2: Gemini native TTS provider + loudnorm`.

---

## Checkpoint D — Caption animation  *(fixes #3 — the headline visual upgrade)*
Two layers: a **pure** timeline builder + a renderer, so the engine is swappable.
- `app/services/captions.py` (**new, pure & unit-tested** like `subtitles.py`):
  consume whisper words → group into 1–3-word on-screen chunks → attach active
  timing + `emphasis` flags (emphasis optionally sourced from Gemini keywords).
  Emit the **engine-agnostic timeline JSON** contract.
- `app/services/captions_moviepy.py` (**new**): read the timeline JSON, build the
  animated caption layer — per-word pop/scale-in + active-word highlight (accent
  color + scale) via easing functions of `t`, composited over the background.
  Bundled display font (Montserrat ExtraBold / Anton), lower/upper-third. Lazy
  import MoviePy; runs behind the B render-job boundary (timeout + stderr
  surfacing).
- `pipeline.render_reel`: branch on `settings.caption_engine`
  (`moviepy` default | `ass` light fallback | `remotion` future). ASS builder
  stays as the fast fallback.
- **Tests:** timeline grouping/timing/emphasis assertions against mock whisper
  words (the pure layer); engine-selection branch. MoviePy render itself is an
  integration check, not a unit test. **Commit:** `v2: caption timeline + MoviePy
  animated captions`.

---

## Checkpoint E — Video polish  *(fixes #4 — soft/flat)*
- `app/services/compose.py` `build_ffmpeg_cmd`: add Ken Burns zoom/pan on the
  background; gradient/vignette overlay behind captions; switch to h264 high
  profile `crf ~18` (from `veryfast`/`crf 23`). Keep the arg builder pure so the
  existing `test_compose.py` style assertions extend cleanly.
- Note in `ACTION_ITEMS.md`: higher-res 1080×1920 source clips improve output.
- **Tests:** extend ffmpeg-arg assertions (zoompan/overlay present, crf 18).
  **Commit:** `v2: Ken Burns + gradient overlay + crf18 encode`.

---

## Checkpoint F — Music + user asset selection  *(replaces pure-random)*
Uses the `Project.background`/`music` columns from A.
- `app/services/compose.py`: accept an optional chosen `background` and a `music`
  path; loop/trim music to reel length, fade in/out, **duck under narration**
  (`sidechaincompress`), `loudnorm` the final mix. `music=none` → narration only
  (current behavior). Background omitted → today's random pick.
- New `app/routers/assets.py`: `GET /api/assets/backgrounds`,
  `GET /api/assets/music` list the pools (basenames).
- `app/routers/projects.py` compile request gains optional `background` + `music`.
  **Security:** whitelist — resolve only against the listed pool by exact
  basename, reject path traversal *before* it reaches the ffmpeg argv (mirror
  `pick_background`). Persist chosen names on the project row.
- **Tests:** whitelist rejects `../` and unknown names; mix arg builder is pure +
  asserted; `music=none` skips the music input. **Commit:** `v2: music ducking +
  whitelisted background/music selection`.

---

## Checkpoint G — Release gate: closed signup + email auth + admin  *(HARD pre-deploy blocker)*
Builds on A's `email` + `is_admin`. **App is not deploy-safe until this lands.**
- **Bootstrap:** on startup, auto-promote `ADMIN_EMAIL` to `is_admin=True` (so
  there's a way in once signup closes). Verify this works *before* removing
  `register` to avoid lockout.
- **Close signup:** remove `POST /api/auth/register` (preferred) — keep
  `login`/`logout`/`me`. Account creation moves to admin flow.
- New `app/routers/admin.py`, every route behind an `is_admin` dependency:
  `GET/POST /api/admin/users`, `PATCH /api/admin/users/{id}`,
  `POST /api/admin/users/{id}/reset-password`, `DELETE /api/admin/users/{id}`
  (cascade projects). No password hashes ever leave the server.
- **Guardrails:** cannot delete/de-admin the last remaining admin; reuse bcrypt +
  email-uniqueness; audit-log admin mutations.
- **Tests:** non-admin gets 403 on every admin route; last-admin guardrail; admin
  create→login round-trip; register endpoint gone. **Commit:** `v2: admin user
  mgmt + closed signup + email auth gate`.

---

## Checkpoint H — Responsive, mobile-first UI
Frontend pass covering the new surfaces from C–G.
- `index.html`/`style.css`/`app.js`: add `<meta name=viewport>`; mobile-first
  fluid flex/grid + a few `max-width` breakpoints; controls, background/music
  pickers (grids from F), and gallery reflow to one column on narrow screens.
- Touch ergonomics: tap targets ≥44 px, no hover-only affordances, correct mobile
  input keyboards, 9:16 preview fits viewport with no horizontal scroll.
- Login-only auth UI (signup removed per G); **Admin page** (visible only when
  `is_admin`) with the user table + create/edit/reset/delete actions — responsive
  too.
- **Verify:** manual check at ~375 px up through desktop (the `/run` skill).
  **Commit:** `v2: mobile-first responsive UI + admin page`.

---

## Checkpoint I — Docker & assets
- `Dockerfile`: add MoviePy + its PIL/ffmpeg needs (no Node/Chromium); bundle
  display fonts (Montserrat ExtraBold / Anton).
- `docker-compose.yml`: mount `MUSIC_FOLDER_PATH` **read-only** (mirror the
  backgrounds mount), default `./music`.
- **Verify:** `docker compose up --build` renders one reel end-to-end with Gemini
  TTS + MoviePy captions + ducked music. **Commit:** `v2: docker — moviepy, fonts,
  music mount`.

---

## Checkpoint J — Backup & restore  *(pre-deploy, not urgent)*
Per `ROADMAP.md` §Backup. Not a code feature — ops runbook + cron.
- Host cron: `sqlite3 .backup` *inside the container* → push to versioned,
  SSE-encrypted S3 bucket with lifecycle retention. Never `cp` the live `app.db`.
- One real restore drill on a throwaway host (down → swap file as root → up).
- **Done when** the pre-deployment checklist in `ROADMAP.md` is ticked.

---

## Cross-cutting invariants (every checkpoint)
- Heavy deps (`google-genai`, `moviepy`, `faster-whisper`, `edge-tts`) imported
  **inside functions**, never module top.
- All subprocess work = explicit `list[str]` argv, no `shell=True`, timeout,
  check `returncode`, surface `stderr`, write under `data/projects/<id>/`.
- Every project/asset access scoped by JWT `user_id`; asset selections
  whitelisted against the pools.
- Pure helpers (`subtitles.py`, new `captions.py`, ffmpeg/mix arg builders) stay
  pure and carry the unit tests; mock SDKs/network in tests.
- `python -m compileall app` + `pytest tests/ -q` green before each commit.

## Suggested order
0 → A → B → C → D → E → F → G → H → I → J.
C–F are the quality payload; G is the hard gate before exposing the app.
