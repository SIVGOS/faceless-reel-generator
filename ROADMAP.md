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

### 6. Admin user management  *(operational — multi-tenant control)*
- **Admin role:** add an `is_admin` flag on `users` (default `false`); seed/promote
  the first admin via env or a one-off script. Gate all admin endpoints on the JWT
  user's `is_admin` — server-side, never trust the client.
- **Admin API** (new `app/routers/admin.py`, all behind an `is_admin` dependency):
  - `GET /api/admin/users` — list users (id, email, created, `is_admin`,
    project count). No password hashes ever leave the server.
  - `POST /api/admin/users` — **create** a user (email + initial password,
    optional `is_admin`).
  - `PATCH /api/admin/users/{id}` — **edit** (email, `is_admin`).
  - `POST /api/admin/users/{id}/reset-password` — **reset password** (admin sets a
    new one; re-hash via the existing `passlib` path).
  - `DELETE /api/admin/users/{id}` — **delete** a user and cascade their projects.
- **Guardrails:** an admin cannot delete or de-admin themselves into a state with
  **zero admins** left; reuse the existing bcrypt hashing + email-uniqueness rules;
  audit-log admin mutations.
- **Frontend:** a separate **Admin page** (visible only when `is_admin`) — user
  table with create / edit / reset-password / delete actions.

### 7. Responsive, mobile-first UI  *(target audience is on phones)*
- **Assumption:** most users open this in a **mobile browser** (we target Instagram
  creators), so the single-page UI must be **mobile-first**, scaling up to desktop —
  not the reverse.
- Fluid layout with CSS flex/grid + a few `max-width` breakpoints; controls,
  pickers (background/music grids from #5), and the project gallery reflow to a
  single column on narrow screens.
- **Touch ergonomics:** tap targets ≥44 px, no hover-only affordances, inputs use
  correct mobile keyboard types, the 9:16 preview fits the viewport without
  horizontal scroll.
- Add the `<meta name="viewport">` tag; test at ~375 px width up through desktop.
- The new **Admin page** (#6) is responsive too.

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
| `ADMIN_EMAIL` | email auto-promoted to admin on startup (bootstrap first admin) |
| `EMAIL_*` | transactional email provider creds (Mailjet/SendGrid; SMTP or API) + verified sender — only for self-service password reset (later) |

## Schema / API additions
- `projects`: add `background` and `music` columns (chosen basenames; `music`
  nullable = no music) for reproducible re-renders + gallery display.
- `users`: add `is_admin` boolean column (default `false`).
- New: `GET /api/assets/backgrounds`, `GET /api/assets/music` (list pools).
- New (admin-only): `GET/POST /api/admin/users`, `PATCH /api/admin/users/{id}`,
  `POST /api/admin/users/{id}/reset-password`, `DELETE /api/admin/users/{id}`.
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

---

## 🔴 Pre-deployment hardening — disable public signup (HIGH PRIORITY)
**This app costs real money per render (Gemini + TTS). Public self-signup must be
closed before deployment — only an admin creates accounts.** This is a hard
release gate, not a polish item.

- **Current state (open door):** `POST /api/auth/register` (`app/routers/auth.py`)
  lets *anyone* create an account and immediately get a session cookie. That must
  not ship as-is.
- **Required change:** registration is **admin-only**. Account creation moves to
  the admin user-management flow (§6 `POST /api/admin/users`). Options for the
  public endpoint, in order of preference:
  1. **Remove** `POST /api/auth/register` entirely (cleanest — there is no
     self-serve path). Keep `login` / `logout` / `me`.
  2. Or keep it but **gate it behind `is_admin`** (reuses the §6 admin dependency).
- **Frontend:** drop the "Sign up" UI from the single-page app; show **login
  only**. New users are told to ask an admin for an account.
- **Bootstrap:** the first admin is seeded via `ADMIN_EMAIL` (see §6 / config) so
  there is a way in once signup is closed — verify this works before removing
  `register`, or you can lock yourself out.
- **Tenancy reminder:** closing signup limits *who* can spend money; per-user cost
  controls (render quotas / rate limits) remain a separate, later concern.

### Identifier: email for everyone (decided)
**All users — admins included — authenticate with email + password.** The current
`users` model / `UserCreate` schema key on **`username`**; migrate the auth layer
to **email** as part of this gate:
- Rename/replace the `username` column with `email` (unique, lowercased, format-
  validated); update `UserCreate`/`UserOut` schemas, `login`, and the admin
  create/edit flows (§6) to match. SQLite needs an `ALTER TABLE` / rebuild for the
  rename — fold into the v2 migration step.
- Email is the natural account key and **enables the password-reset flow below**.

### Password reset flow (enabled by email)
- **Admin-initiated (ships first, already in §6):** `POST /api/admin/users/{id}/
  reset-password` lets an admin set a new password. Sufficient for launch.
- **Self-service (later, optional):** "forgot password" → email a signed,
  short-lived reset token → user sets a new password. Requires a **transactional
  email provider — likely Mailjet or SendGrid** (SMTP/API) — a new dependency +
  `EMAIL_*` config and a provider account/API key, so it's a follow-on, not a
  launch blocker. Tokens single-use + expiring; never reveal whether an email
  exists (anti-enumeration). **User prerequisite:** sign up for the provider and
  supply an API key + a verified sender domain/address — see `ACTION_ITEMS.md`.

---

## Backup & restore (pre-deployment, not urgent)
The SQLite DB (`data/app.db`) is the only stateful, irreplaceable asset (rendered
reels under `data/projects/` are regenerable). We want an off-box backup before
going live, but it doesn't block current build work.

### Plan: periodic SQLite snapshot → S3
- **Cadence:** host cron pushes a snapshot to S3 every few hours.
- **Consistency (important):** do **not** `cp`/`aws s3 cp` the live `app.db` — a
  copy taken mid-write can be torn/inconsistent. Use SQLite's online backup to get
  a clean single-file snapshot:
  ```bash
  # Run inside the container — already root, file always reachable, consistent.
  docker compose exec -T app \
    sqlite3 /app/data/app.db ".backup '/app/data/backup.db'"
  # backup.db lands in host ./data via the bind mount → push to S3.
  aws s3 cp ./data/backup.db s3://<bucket>/reel-forge/app-$(date +%F-%H%M).db
  ```
  (`VACUUM INTO` is an alternative that also compacts.)
- **Retention:** keep N hourly + a few daily; lifecycle-expire the rest on the
  bucket. Versioned bucket + SSE recommended.

### Permissions caveat (root-owned bind mount)
- The container runs as **root** (no `USER` in the Dockerfile) and `./data` is a
  bind mount, so `data/app.db` on the host is **root-owned**, mode `0644`.
- **Backup (read):** fine — file is world-readable; taking the snapshot *inside the
  container* sidesteps host ownership entirely (preferred).
- **Restore (write):** must run **as root / sudo** — a non-root user can't replace
  the root-owned file or create sidecar files in the root-owned dir.
- *Optional fix:* set `user: "<uid>:<gid>"` in `docker-compose.yml` so `data/` is
  owned by the host user and both directions work without sudo (the host `./data`
  must be pre-owned by that uid before first run).

### Restore runbook (safe order)
SQLite holds `app.db` open while the app runs — never swap it underneath a live
container:
1. `docker compose down` (stop the app).
2. As **root**, place the restored file at `./data/app.db` and remove any stale
   `-journal` / `-wal` / `-shm` sidecars.
3. `docker compose up -d` — startup re-opens the file cleanly (`init_db()` is a
   no-op on an existing, populated DB).

### Pre-deployment checklist
- [ ] Backup cron installed (root crontab) + S3 bucket (versioning + SSE + lifecycle).
- [ ] One real restore drill on a throwaway host (prove the runbook end-to-end).
- [ ] Decide DB-write durability later if we move off SQLite (e.g. Litestream for
      continuous replication, or Postgres) — out of scope for v2.
