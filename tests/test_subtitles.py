"""Offline sanity assertions for the pure .ass caption builder."""
from __future__ import annotations

from app.services import subtitles

MOCK_WORDS = [
    {"text": "Resilience", "start": 0.0, "end": 0.6},
    {"text": "is", "start": 0.6, "end": 0.8},
    {"text": "forged", "start": 0.8, "end": 1.3},
    {"text": "in", "start": 1.3, "end": 1.45},
    {"text": "fire", "start": 1.45, "end": 2.0},
    {"text": "always", "start": 2.0, "end": 2.7},
]


def test_fmt_time_centiseconds():
    assert subtitles._fmt_time(0) == "0:00:00.00"
    assert subtitles._fmt_time(2.5) == "0:00:02.50"
    assert subtitles._fmt_time(3661.23) == "1:01:01.23"
    # never emit a negative timestamp
    assert subtitles._fmt_time(-5) == "0:00:00.00"


def test_normalize_clamps_nonmonotonic():
    raw = [
        {"text": "a", "start": 1.0, "end": 0.5},   # end before start
        {"text": "", "start": 1.0, "end": 2.0},    # empty -> dropped
        {"text": "b", "start": 0.2, "end": 0.3},   # start before prev end
    ]
    words = subtitles.normalize_words(raw)
    assert [w.text for w in words] == ["a", "b"]
    for w in words:
        assert w.end > w.start
    # monotonic non-decreasing starts
    assert words[1].start >= words[0].end


def test_build_ass_structure_and_karaoke():
    doc = subtitles.build_ass(MOCK_WORDS, max_words_per_line=5)
    assert "[Script Info]" in doc
    assert "PlayResX: 1080" in doc
    assert "PlayResY: 1920" in doc
    assert "Style: Karaoke" in doc
    # active = yellow, secondary = white
    assert subtitles.ACTIVE_COLOR in doc
    assert subtitles.BASE_COLOR in doc
    # 6 words / 5-per-line => 2 dialogue lines
    dialogues = [ln for ln in doc.splitlines() if ln.startswith("Dialogue:")]
    assert len(dialogues) == 2
    # karaoke tags present
    assert "\\k" in doc
    # ends on a trailing newline
    assert doc.endswith("\n")


def test_build_ass_escapes_braces():
    doc = subtitles.build_ass([{"text": "a{b}c", "start": 0.0, "end": 0.5}])
    assert "a\\{b\\}c" in doc


def test_write_ass_roundtrip(tmp_path):
    out = subtitles.write_ass(MOCK_WORDS, tmp_path / "nested" / "cap.ass")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("[Script Info]")
