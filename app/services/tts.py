"""Narration synthesis with a pluggable provider seam.

Two providers behind one entry point, `synthesize`, dispatched on
`settings.tts_provider`:

- ``gemini`` — native Gemini TTS (quality default). Reuses the existing
  ``google-genai`` SDK + ``GEMINI_API_KEY``. The model returns raw 24 kHz /
  16-bit / mono PCM, which we wrap in a WAV container (stdlib ``wave``) and then
  loudness-normalise (EBU R128 via ffmpeg ``loudnorm``). faster-whisper reads
  the resulting WAV directly. On any failure we optionally fall back to edge.
- ``edge`` — the original free ``edge-tts`` path (mp3 out).

Heavy SDKs (``google-genai``, ``edge_tts``) are imported lazily inside the
provider functions. The pure, unit-tested helpers are ``pcm_to_wav`` (PCM →
WAV) and ``build_loudnorm_cmd`` (the ffmpeg argv).
"""
from __future__ import annotations

import asyncio
import subprocess
import wave
from pathlib import Path

from ..config import settings
from .language import contains_devanagari


class TTSError(RuntimeError):
    pass


# Gemini TTS audio format: signed 16-bit little-endian PCM, 24 kHz, mono.
GEMINI_TTS_SAMPLE_RATE = 24000
GEMINI_TTS_SAMPLE_WIDTH = 2  # bytes (16-bit)
GEMINI_TTS_CHANNELS = 1

# EBU R128 loudness target — consistent perceived loudness across reels.
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def synthesize(text: str, out_path: str | Path, voice: str | None = None) -> Path:
    """Synthesize `text` to audio near `out_path`, returning the path written.

    The provider chooses the container, so the returned path may differ from
    `out_path`'s suffix (gemini → ``.wav``, edge → ``.mp3``). Callers must use
    the returned path downstream rather than assuming `out_path`.
    """
    provider = (settings.tts_provider or "gemini").strip().lower()

    if provider == "edge":
        return _synthesize_edge(text, out_path, voice)

    if provider == "gemini":
        try:
            return _synthesize_gemini(text, out_path, voice)
        except TTSError:
            if settings.tts_fallback_to_edge:
                # Fall back to edge's own configured default voice — `voice`
                # here is a Gemini voice name and is meaningless to edge-tts.
                return _synthesize_edge(text, out_path, None)
            raise

    raise TTSError(f"Unknown TTS provider: {settings.tts_provider!r} (use 'gemini' or 'edge').")


# --------------------------------------------------------------------------- #
# Gemini provider
# --------------------------------------------------------------------------- #
def _synthesize_gemini(text: str, out_path: str | Path, voice: str | None) -> Path:
    """Gemini native TTS → loudness-normalised WAV. Returns the WAV path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out_path.parent / (out_path.stem + ".raw.wav")
    wav_path = out_path.parent / (out_path.stem + ".wav")

    pcm = _request_gemini_pcm(text, voice)
    pcm_to_wav(pcm, raw_path)

    cmd = build_loudnorm_cmd(raw_path, wav_path)
    _run_ffmpeg(cmd, timeout=settings.render_timeout_seconds)
    raw_path.unlink(missing_ok=True)

    if not wav_path.exists() or wav_path.stat().st_size == 0:
        raise TTSError("Gemini TTS loudnorm produced no audio output.")
    return wav_path


def _request_gemini_pcm(text: str, voice: str | None) -> bytes:
    """Call Gemini TTS and return raw PCM bytes (24 kHz / 16-bit / mono)."""
    if not settings.gemini_api_key:
        raise TTSError("GEMINI_API_KEY is not configured. Set it in .env.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on install
        raise TTSError("google-genai is not installed. `pip install google-genai`.") from exc

    voice = voice or settings.tts_gemini_voice
    # Devanagari (Hindi/Sanskrit) → the Indian-accent director prompt so the verse
    # is pronounced correctly and any English is read in a neutral Indian accent.
    style_prompt = (
        settings.tts_style_prompt_indian
        if contains_devanagari(text)
        else settings.tts_style_prompt
    )
    style = (style_prompt or "").strip()
    contents = f"{style}\n\n{text}" if style else text

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.tts_gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        )
                    )
                ),
            ),
        )
    except Exception as exc:  # SDK raises a variety of error types
        raise TTSError(f"Gemini TTS request failed: {exc}") from exc

    pcm = _extract_pcm(response)
    if not pcm:
        raise TTSError("Gemini TTS returned no audio data.")
    return pcm


def _extract_pcm(response) -> bytes:
    """Pull inline PCM bytes out of a Gemini response, defensively."""
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError, TypeError):
        return b""
    for part in parts or []:
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None) if inline is not None else None
        if data:
            return data
    return b""


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested, no network / no SDK)
# --------------------------------------------------------------------------- #
def pcm_to_wav(pcm: bytes, wav_path: str | Path) -> Path:
    """Wrap raw 24 kHz / 16-bit / mono PCM in a WAV container."""
    wav_path = Path(wav_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(GEMINI_TTS_CHANNELS)
        w.setsampwidth(GEMINI_TTS_SAMPLE_WIDTH)
        w.setframerate(GEMINI_TTS_SAMPLE_RATE)
        w.writeframes(pcm)
    return wav_path


def build_loudnorm_cmd(in_path: str | Path, out_path: str | Path) -> list[str]:
    """ffmpeg argv to loudness-normalise `in_path` to a 24 kHz mono WAV."""
    return [
        "ffmpeg",
        "-y",
        "-i", str(in_path),
        "-af", LOUDNORM_FILTER,
        "-ar", str(GEMINI_TTS_SAMPLE_RATE),
        "-ac", str(GEMINI_TTS_CHANNELS),
        "-c:a", "pcm_s16le",
        str(out_path),
    ]


def _run_ffmpeg(cmd: list[str], timeout: int) -> None:
    """Run an ffmpeg argv as an explicit no-shell subprocess, surfacing stderr."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing dependent
        raise TTSError(f"ffmpeg loudnorm timed out after {timeout}s") from exc
    except FileNotFoundError as exc:  # pragma: no cover - depends on install
        raise TTSError("ffmpeg not found. Install ffmpeg (bundled in the Docker image).") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise TTSError(f"ffmpeg loudnorm failed (exit {proc.returncode}):\n{tail}")


# --------------------------------------------------------------------------- #
# Edge provider (free fallback) — original implementation
# --------------------------------------------------------------------------- #
def _synthesize_edge(text: str, out_path: str | Path, voice: str | None = None) -> Path:
    """Render `text` to an .mp3 at `out_path` using edge-tts.

    Runs the async edge-tts API to completion on a private event loop so it is
    safe to call from FastAPI's sync threadpool.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # No explicit voice → pick by script: an Indian voice reads Devanagari (and the
    # English around it) far better than the default en-US voice.
    if voice is None:
        voice = (
            settings.tts_voice_indian
            if contains_devanagari(text)
            else settings.tts_voice
        )

    try:
        import edge_tts
    except ImportError as exc:  # pragma: no cover - depends on install
        raise TTSError("edge-tts is not installed. `pip install edge-tts`.") from exc

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise TTSError(f"edge-tts synthesis failed: {exc}") from exc

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TTSError("edge-tts produced no audio output.")
    return out_path
