"""Pure-Python builder for Advanced SubStation Alpha (.ass) karaoke captions.

Takes plain word/timestamp dicts (as produced by faster-whisper) and emits an
``.ass`` string with karaoke-style highlighting: the active word glows bright
yellow while the rest of the phrase stays white, centered for a 9:16 frame.

This module imports nothing heavy on purpose — it is the layer covered by
offline sanity tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 9:16 canvas the captions are authored against. FFmpeg renders the .ass at
# this resolution and scales to the video.
PLAY_RES_X = 1080
PLAY_RES_Y = 1920

ACTIVE_COLOR = "&H0000FFFF"  # ASS BGR: bright yellow
BASE_COLOR = "&H00FFFFFF"    # white
OUTLINE_COLOR = "&H00000000" # black

# Group words into short phrases so a few words show at once (typical reel look).
MAX_WORDS_PER_LINE = 5


@dataclass
class Word:
    text: str
    start: float  # seconds
    end: float    # seconds


def _fmt_time(seconds: float) -> str:
    """Format seconds as ASS timestamp H:MM:SS.cc (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    """Escape characters with meaning in ASS dialogue text."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def normalize_words(raw: list[dict]) -> list[Word]:
    """Coerce whisper-style word dicts into clean, monotonic Word objects.

    Accepts dicts with ``word``/``text`` and ``start``/``end``. Skips empty
    tokens and clamps any end-before-start glitches from the aligner.
    """
    words: list[Word] = []
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
        words.append(Word(text=text, start=start, end=end))
        prev_end = end
    return words


def _group_lines(words: list[Word], max_words: int) -> list[list[Word]]:
    return [words[i : i + max_words] for i in range(0, len(words), max_words)]


def build_ass(
    raw_words: list[dict],
    *,
    font: str = "Arial",
    font_size: int = 96,
    max_words_per_line: int = MAX_WORDS_PER_LINE,
) -> str:
    """Build a complete .ass document string from word timestamps.

    Each phrase becomes one Dialogue line spanning its words. Within the line,
    ``\\k`` karaoke tags advance the highlight word-by-word using the per-word
    durations, so the active word turns yellow in sync with the narration.
    """
    words = normalize_words(raw_words)
    lines = _group_lines(words, max(1, max_words_per_line))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_RES_X}
PlayResY: {PLAY_RES_Y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{font_size},{ACTIVE_COLOR},{BASE_COLOR},{OUTLINE_COLOR},&H64000000,-1,0,0,0,100,100,0,0,1,4,2,5,80,80,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for line in lines:
        if not line:
            continue
        start = line[0].start
        end = line[-1].end
        parts: list[str] = []
        for w in line:
            # \k duration is in centiseconds; secondary->primary swap is what
            # produces the active-word highlight.
            dur_cs = max(1, int(round((w.end - w.start) * 100)))
            parts.append(f"{{\\k{dur_cs}}}{_ass_escape(w.text)} ")
        text = "".join(parts).rstrip()
        events.append(
            f"Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},Karaoke,,0,0,0,,{text}"
        )

    return header + "\n".join(events) + "\n"


def write_ass(raw_words: list[dict], out_path: str | Path, **kwargs) -> Path:
    """Build the .ass document and write it to ``out_path`` (UTF-8)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_ass(raw_words, **kwargs), encoding="utf-8")
    return out_path
