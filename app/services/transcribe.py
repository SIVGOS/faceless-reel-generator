"""Word-level alignment via faster-whisper (CPU, int8). Imported lazily."""
from __future__ import annotations

from pathlib import Path

from ..config import settings

# Cache each loaded model by name across requests — loading is the expensive part.
# Devanagari reels use a larger model than English ones, so more than one may load.
_models: dict[str, object] = {}


class TranscriptionError(RuntimeError):
    pass


def _get_model(model_name: str):
    model = _models.get(model_name)
    if model is not None:
        return model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on install
        raise TranscriptionError(
            "faster-whisper is not installed. `pip install faster-whisper`."
        ) from exc
    # int8 keeps it lean enough for CPU-only containers.
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    _models[model_name] = model
    return model


def transcribe_words(audio_path: str | Path, *, language: str | None = None) -> list[dict]:
    """Return a list of {text, start, end} word dicts for the audio file.

    ``language`` is a whisper language hint (e.g. ``"hi"`` for Devanagari content).
    When set, the larger ``whisper_model_devanagari`` is used — ``base`` aligns
    Devanagari poorly; when ``None``, English uses the default ``whisper_model``
    with auto language detection.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise TranscriptionError(f"Audio file not found: {audio_path}")

    model_name = settings.whisper_model_devanagari if language else settings.whisper_model
    model = _get_model(model_name)
    try:
        segments, _info = model.transcribe(
            str(audio_path), word_timestamps=True, language=language
        )
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
