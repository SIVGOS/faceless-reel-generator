# Action Items (for the user) — before v2 build

Most of this is reassuring: your current setup mostly already works for v2.

## Google API key — what you DON'T need to do
- **No new API to enable.** Gemini native TTS uses the *same* `google-genai` SDK
  and the *same* AI Studio `GEMINI_API_KEY` you already have for script
  generation.
- **No GCP project or service account** needed for the recommended TTS model.
- The recommended model `gemini-3.1-flash-tts-preview` is **available on the free
  tier** (with restrictive preview rate limits).

## Google API key — what to verify / decide
1. **Quick capability check (we'll script this in-session):** confirm your key can
   call `gemini-3.1-flash-tts-preview` and that the preview model is available in
   your region. Preview models can change.
2. **Free vs paid tier:** free tier works but has tight rate limits. For smooth
   multi-render use you may want to **enable billing**. ⚠️ Note: enabling billing
   on a project **removes the free tier for that whole project** — every Gemini
   call (including script generation) becomes billable from the first token.
   Decide whether to use a **separate project/key** for paid TTS vs free script
   generation.
3. **Cost awareness:** Gemini TTS is **not free like edge-tts**. Ballpark:
   `gemini-3.1-flash-tts-preview` ≈ $20 / 1M audio output tokens; a ~40s reel is a
   small fraction of that, but it's non-zero per render.

## Only if you later want PRECISE pronunciation control (the SSML escape hatch)
This is **optional** and only if Gemini TTS still mispronounces a specific word:
- Enable the **Cloud Text-to-Speech API** in a GCP project.
- Create a **service account** + credential (or Cloud API key) — this is separate
  from your AI Studio key.
- Ensure **billing** is enabled on that GCP project.

## Caption engine decision (blocks the captions work, not the voice work)
- **Choose Remotion vs MoviePy.**
  - Remotion = best animation fidelity, but heavier Docker image (Node +
    Chromium) and a **licensing check**: it's free for individuals/small
    companies but needs a paid **Company License** above a size threshold —
    confirm whether `SIVGOS` qualifies for free use.
  - MoviePy = pure-Python, lighter, MIT-licensed, slightly lower fidelity.

## Assets (improves output quality directly)
- Add a few **high-resolution 1080×1920 .mp4** clips to your
  `BG_VIDEO_FOLDER_PATH` library (quality in = quality out).
- Optional: a small folder of **background music** tracks if you want music with
  ducking in v2.

## Nothing else is required right now
We'll handle all code, Docker, and config changes in the build sessions.
