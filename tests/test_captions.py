"""Offline sanity assertions for the pure caption timeline + easing helpers.

No MoviePy import here: `captions_moviepy` keeps the heavy SDK inside
`render_reel`, so its module-level easing functions are importable and testable.
"""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.services import captions, captions_moviepy as cmp

MOCK_WORDS = [
    {"text": "Resilience", "start": 0.0, "end": 0.6},
    {"text": "is", "start": 0.6, "end": 0.8},
    {"text": "forged", "start": 0.8, "end": 1.3},
    {"text": "in", "start": 1.3, "end": 1.45},
    {"text": "fire.", "start": 1.45, "end": 2.0},
    {"text": "Always", "start": 2.0, "end": 2.7},
]


# --------------------------------------------------------------------------- #
# Timeline builder
# --------------------------------------------------------------------------- #
def test_build_timeline_grouping_and_frame():
    tl = captions.build_timeline(MOCK_WORDS, max_words_per_chunk=3)
    assert tl["version"] == captions.TIMELINE_VERSION
    assert tl["frame"] == {"width": 1080, "height": 1920}
    chunks = tl["chunks"]
    # "Resilience is forged" (3) | "in fire." (sentence break) | "Always"
    assert [[w["text"] for w in c["words"]] for c in chunks] == [
        ["Resilience", "is", "forged"],
        ["in", "fire."],
        ["Always"],
    ]


def test_chunk_timing_spans_its_words():
    tl = captions.build_timeline(MOCK_WORDS, max_words_per_chunk=3)
    first = tl["chunks"][0]
    assert first["start"] == 0.0
    assert first["end"] == 1.3  # last word ("forged") end


def test_emphasis_matches_normalized_keywords():
    tl = captions.build_timeline(MOCK_WORDS, emphasis_keywords=["FIRE", "resilience"])
    flat = {w["text"]: w["emphasis"] for c in tl["chunks"] for w in c["words"]}
    # case-insensitive + trailing punctuation stripped for the match
    assert flat["Resilience"] is True
    assert flat["fire."] is True
    assert flat["forged"] is False


def test_build_timeline_clamps_nonmonotonic():
    raw = [
        {"text": "a", "start": 1.0, "end": 0.5},   # end before start
        {"text": "", "start": 1.0, "end": 2.0},    # empty -> dropped
        {"text": "b", "start": 0.2, "end": 0.3},   # start before prev end
    ]
    tl = captions.build_timeline(raw, max_words_per_chunk=5)
    words = [w for c in tl["chunks"] for w in c["words"]]
    assert [w["text"] for w in words] == ["a", "b"]
    for w in words:
        assert w["end"] > w["start"]
    assert words[1]["start"] >= words[0]["end"]  # monotonic


def test_build_timeline_empty_raises():
    with pytest.raises(captions.CaptionError):
        captions.build_timeline([])


def test_write_timeline_roundtrip(tmp_path):
    tl, path = captions.build_and_write(MOCK_WORDS, tmp_path / "nested" / "cap.json")
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == tl


# --------------------------------------------------------------------------- #
# Easing helpers (pure, no MoviePy)
# --------------------------------------------------------------------------- #
def test_clamp01():
    assert cmp.clamp01(-1) == 0.0
    assert cmp.clamp01(0.5) == 0.5
    assert cmp.clamp01(2) == 1.0


def test_ease_out_back_endpoints_and_overshoot():
    assert cmp.ease_out_back(0) == pytest.approx(0.0, abs=1e-9)
    assert cmp.ease_out_back(1) == pytest.approx(1.0, abs=1e-9)
    # overshoots above 1.0 before settling (the "back" pop)
    assert max(cmp.ease_out_back(p / 100) for p in range(101)) > 1.0


def test_pop_scale_bounds():
    assert cmp.pop_scale(-0.1) == cmp.POP_MIN_SCALE  # before start: tiny, not 0
    assert cmp.pop_scale(0.0) == cmp.POP_MIN_SCALE
    assert cmp.pop_scale(cmp.POP_DURATION) == 1.0     # settled
    assert cmp.pop_scale(10.0) == 1.0                 # well past
    mid = cmp.pop_scale(cmp.POP_DURATION / 2)
    assert cmp.POP_MIN_SCALE < mid                    # growing


def test_centered_position_recenters_with_scale():
    pos = cmp._centered_position(500.0, 1000.0, 200.0, 100.0, scale_fn=lambda t: 1.0)
    # at scale 1.0 the top-left is centre minus half size
    assert pos(0) == (400.0, 950.0)


# --------------------------------------------------------------------------- #
# Config wiring
# --------------------------------------------------------------------------- #
def test_bundled_font_exists():
    assert settings.caption_font_path.exists(), "Anton font must ship with the app"
