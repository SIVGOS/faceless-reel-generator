"""Pure-Python caption *timeline* builder — the engine-agnostic contract.

Takes plain word/timestamp dicts (as produced by faster-whisper) and emits a
small, JSON-serialisable **timeline** describing what text is on screen, when,
and which word is active. Renderers (`captions_moviepy.py` today; a Remotion
project tomorrow) consume this same JSON, so swapping the animation engine never
touches this layer.

Like `subtitles.py`, this module imports nothing heavy — it is the layer covered
by offline sanity tests.

Timeline shape (version 1):
    {
      "version": 1,
      "frame": {"width": 1080, "height": 1920},
      "chunks": [
        {
          "start": 0.0, "end": 1.3,
          "words": [
            {"text": "Resilience", "start": 0.0, "end": 0.6, "emphasis": true},
            {"text": "is",         "start": 0.6, "end": 0.8, "emphasis": false}
          ]
        },
        ...
      ]
    }
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 9:16 canvas the captions are authored against (mirrors subtitles.py).
FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

# Reels show a few words at a time so the active word is easy to track.
MAX_WORDS_PER_CHUNK = 3

# A word ending in one of these closes its chunk early, so phrases break on
# natural sentence/clause boundaries rather than mid-thought.
_CHUNK_BREAK_CHARS = ".!?"

TIMELINE_VERSION = 1


class CaptionError(RuntimeError):
    """Raised when a timeline cannot be built or rendered."""


def _normalize_token(text: str) -> str:
    """Lowercase + strip surrounding punctuation for emphasis matching."""
    return re.sub(r"[^0-9a-z]+", "", text.lower())


def _normalize_keywords(keywords) -> set[str]:
    if not keywords:
        return set()
    return {_normalize_token(k) for k in keywords if _normalize_token(k)}


def _clean_words(raw: list[dict]) -> list[dict]:
    """Coerce whisper-style dicts into clean, monotonic word dicts.

    Accepts ``word``/``text`` and ``start``/``end``. Drops empty tokens and
    clamps end-before-start / overlap glitches from the aligner (same rules as
    ``subtitles.normalize_words``).
    """
    words: list[dict] = []
    prev_end = 0.0
    for item in raw:
        text = (item.get("word") if "word" in item else item.get("text", "")) or ""
        text = text.strip()
        if not text:
            continue
        start = float(item.get("start", prev_end))
        end = float(item.get("end", start))
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + 0.05
        words.append({"text": text, "start": start, "end": end})
        prev_end = end
    return words


def build_timeline(
    raw_words: list[dict],
    *,
    emphasis_keywords=None,
    max_words_per_chunk: int = MAX_WORDS_PER_CHUNK,
    frame: tuple[int, int] = (FRAME_WIDTH, FRAME_HEIGHT),
) -> dict:
    """Group word timings into on-screen chunks + emphasis flags.

    Words are grouped into runs of up to ``max_words_per_chunk``; a word ending
    in sentence punctuation closes its chunk early. ``emphasis_keywords`` (e.g.
    sourced from Gemini) flag matching words for accent styling.
    """
    words = _clean_words(raw_words)
    if not words:
        raise CaptionError("No words to build a caption timeline from.")

    kw = _normalize_keywords(emphasis_keywords)
    cap = max(1, max_words_per_chunk)

    chunks: list[dict] = []
    current: list[dict] = []
    for w in words:
        current.append(
            {
                "text": w["text"],
                "start": w["start"],
                "end": w["end"],
                "emphasis": _normalize_token(w["text"]) in kw,
            }
        )
        ends_sentence = w["text"][-1] in _CHUNK_BREAK_CHARS
        if len(current) >= cap or ends_sentence:
            chunks.append(_make_chunk(current))
            current = []
    if current:
        chunks.append(_make_chunk(current))

    return {
        "version": TIMELINE_VERSION,
        "frame": {"width": frame[0], "height": frame[1]},
        "chunks": chunks,
    }


def _make_chunk(words: list[dict]) -> dict:
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "words": list(words),
    }


def write_timeline(timeline: dict, out_path: str | Path) -> Path:
    """Serialise a timeline to JSON at ``out_path`` (UTF-8)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    return out_path


def build_and_write(
    raw_words: list[dict],
    out_path: str | Path,
    **kwargs,
) -> tuple[dict, Path]:
    """Convenience: build the timeline and persist it. Returns (timeline, path)."""
    timeline = build_timeline(raw_words, **kwargs)
    return timeline, write_timeline(timeline, out_path)
