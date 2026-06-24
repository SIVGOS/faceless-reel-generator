"""edge-tts narration. The edge_tts package is imported lazily."""
from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import settings


class TTSError(RuntimeError):
    pass


def synthesize(text: str, out_path: str | Path, voice: str | None = None) -> Path:
    """Render `text` to an .mp3 at `out_path` using edge-tts.

    Runs the async edge-tts API to completion on a private event loop so it is
    safe to call from FastAPI's sync threadpool.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = voice or settings.tts_voice

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
