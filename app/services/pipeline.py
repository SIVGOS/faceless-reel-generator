"""End-to-end render pipeline: script -> audio -> words -> captions -> video.

Each project gets an isolated working directory under data/projects/<id>/ so
concurrent renders never collide on temp files.

The caption stage is engine-selectable (`settings.caption_engine`):
- ``moviepy`` (default) — a pure timeline (`captions.py`) drives the MoviePy
  renderer (`captions_moviepy.py`), which composites the animated caption layer
  over the background and muxes narration itself.
- ``ass`` — the lightweight fallback: the `subtitles.py` karaoke `.ass` burned
  over a background by ffmpeg (`compose.py`). The same path used through v1.
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from . import align, captions, captions_moviepy, compose, subtitles, transcribe, tts
from .language import DEVANAGARI_WHISPER_LANGUAGE, contains_devanagari


def project_dir(project_id: int) -> Path:
    d = settings.projects_dir / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_reel(project_id: int, script: str) -> Path:
    """Run the full chain for one project and return the output .mp4 path.

    Raises the underlying service error (TTSError / TranscriptionError /
    CompositionError / CaptionError) on failure so the caller can record it.
    """
    work = project_dir(project_id)
    audio_path = work / "narration.mp3"
    output_path = work / "reel.mp4"

    # 1. Narration. The provider chooses the container (gemini → loudnorm'd .wav,
    # edge → .mp3), so use the returned path for the downstream stages.
    audio_path = tts.synthesize(script, audio_path)

    # 2. Word-level alignment. Devanagari (Hindi/Sanskrit) content gets a Hindi
    # language hint + the larger whisper model so the spoken verse actually aligns
    # (base with no hint produced zero words for Sanskrit). Detected from the
    # script so an English reel with an embedded shloka is covered too.
    whisper_language = (
        DEVANAGARI_WHISPER_LANGUAGE if contains_devanagari(script) else None
    )
    timed_words = transcribe.transcribe_words(audio_path, language=whisper_language)

    # 2b. Captions must show the EXACT script (whisper mis-spells, esp. Devanagari).
    # Keep whisper's timing but remap it onto the known-correct script text; fall
    # back to the raw whisper words if alignment yields nothing.
    words = align.align_script_to_timings(script, timed_words) or timed_words

    # 3 + 4. Captions + composition, branched by engine.
    engine = (settings.caption_engine or "moviepy").strip().lower()
    if engine == "ass":
        ass_path = work / "captions.ass"
        subtitles.write_ass(words, ass_path)
        compose.compose_video(
            audio_path=audio_path,
            ass_path=ass_path,
            output_path=output_path,
            backgrounds_dir=settings.backgrounds_dir,
            timeout_seconds=settings.render_timeout_seconds,
        )
        return output_path

    if engine == "moviepy":
        timeline, _ = captions.build_and_write(words, work / "captions.json")
        background = compose.pick_background(settings.backgrounds_dir)
        captions_moviepy.render_reel(
            timeline,
            background_path=background,
            audio_path=audio_path,
            output_path=output_path,
        )
        return output_path

    raise captions.CaptionError(
        f"Unknown caption engine: {settings.caption_engine!r} (use 'moviepy' or 'ass')."
    )
