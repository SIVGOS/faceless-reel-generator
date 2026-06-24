# Action Items (for the user) — before v2 build

Good news: your key is already paid-tier, so there's almost nothing to set up.

## Google API key — already sorted
- The key is **already on the paid/billing tier** (free quota used up), so:
  - **No new API to enable.** Gemini native TTS uses the *same* `google-genai`
    SDK and the *same* `GEMINI_API_KEY` you already pay for.
  - **No GCP project or service account** needed.
  - **No tier decision** — billing is already on; all Gemini TTS models are
    available to you, including `gemini-2.5-pro-preview-tts` (quality-optimized),
    which is paid-only.
  - **No need for a separate key/project** — script generation is already
    billable too, so nothing changes by adding TTS.

## Google API key — only thing to verify
- **Quick capability check (we'll script this in-session):** confirm the key can
  call the chosen TTS model (`gemini-3.1-flash-tts-preview` recommended; or
  `gemini-2.5-pro-preview-tts` to A/B for quality) and that it's available in your
  region. These are *preview* models and can change.

## Cost awareness (informational, not an action)
- Gemini TTS bills per audio output token (≈ $20 / 1M for the 3.1-flash and 2.5-pro
  models). A ~40s reel is a small fraction of that, but it's a real per-render cost
  on top of script generation. edge-tts remains available as a free fallback.

## Only if you later want PRECISE pronunciation control (the SSML escape hatch)
This is **optional** and only if Gemini TTS still mispronounces a specific word:
- Enable the **Cloud Text-to-Speech API** in a GCP project.
- Create a **service account** + credential (or Cloud API key) — this is separate
  from your AI Studio key.
- Ensure **billing** is enabled on that GCP project.

## Caption engine — DECIDED (no action needed)
- **MoviePy** chosen (pure-Python, MIT, no licensing cost, lighter image) to
  minimize cost. Remotion kept as a documented fallback if MoviePy's fidelity
  isn't good enough — revisit only then.

## Background music — one small decision
- Decide **yes/no on background music** for v2 (adds a music pool + ducking).

## Assets (improves output quality directly)
- Add a few **high-resolution 1080×1920 .mp4** clips to your
  `BG_VIDEO_FOLDER_PATH` library (quality in = quality out).
- Optional: a small folder of **background music** tracks if you want music with
  ducking in v2.

## Nothing else is required right now
We'll handle all code, Docker, and config changes in the build sessions.
