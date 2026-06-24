"""Word-level alignment via faster-whisper (CPU, int8). Imported lazily."""
from __future__ import annotations

from pathlib import Path

from ..config import settings

# Cache the model across requests — loading is the expensive part.
_model = None


class TranscriptionError(RuntimeError):
    pass


def _get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on install
        raise TranscriptionError(
            "faster-whisper is not installed. `pip install faster-whisper`."
        ) from exc
    # int8 keeps it lean enough for CPU-only containers.
    _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _model


def transcribe_words(audio_path: str | Path) -> list[dict]:
    """Return a list of {text, start, end} word dicts for the audio file."""
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise TranscriptionError(f"Audio file not found: {audio_path}")

    model = _get_model()
    try:
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
    except Exception as exc:
        raise TranscriptionError(f"Transcription failed: {exc}") from exc

    words: list[dict] = []
    for seg in segments:
        for w in getattr(seg, "words", None) or []:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append({"text": text, "start": float(w.start), "end": float(w.end)})

    if not words:
        raise TranscriptionError("No words were aligned from the audio.")
    return words
