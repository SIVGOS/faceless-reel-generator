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
from . import captions, captions_moviepy, compose, subtitles, transcribe, tts


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

    # 2. Word-level alignment
    words = transcribe.transcribe_words(audio_path)

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
