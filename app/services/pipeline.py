"""End-to-end render pipeline: script -> audio -> words -> captions -> video.

Each project gets an isolated working directory under data/projects/<id>/ so
concurrent renders never collide on temp files.
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from . import compose, subtitles, transcribe, tts


def project_dir(project_id: int) -> Path:
    d = settings.projects_dir / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_reel(project_id: int, script: str) -> Path:
    """Run the full chain for one project and return the output .mp4 path.

    Raises the underlying service error (TTSError / TranscriptionError /
    CompositionError) on failure so the caller can record it.
    """
    work = project_dir(project_id)
    audio_path = work / "narration.mp3"
    ass_path = work / "captions.ass"
    output_path = work / "reel.mp4"

    # 1. Narration. The provider chooses the container (gemini → loudnorm'd .wav,
    # edge → .mp3), so use the returned path for the downstream stages.
    audio_path = tts.synthesize(script, audio_path)

    # 2. Word-level alignment
    words = transcribe.transcribe_words(audio_path)

    # 3. Karaoke captions
    subtitles.write_ass(words, ass_path)

    # 4. Compose against a random background
    compose.compose_video(
        audio_path=audio_path,
        ass_path=ass_path,
        output_path=output_path,
        backgrounds_dir=settings.backgrounds_dir,
        timeout_seconds=settings.render_timeout_seconds,
    )
    return output_path
