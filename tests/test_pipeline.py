"""Engine-selection branch tests for the render pipeline.

The heavy stages (TTS, whisper, ffmpeg, MoviePy) are monkeypatched so the test
only exercises the branching logic in `pipeline.render_reel`.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.services import (
    captions,
    captions_moviepy,
    compose,
    pipeline,
    subtitles,
    transcribe,
    tts,
)

MOCK_WORDS = [
    {"text": "Stay", "start": 0.0, "end": 0.4},
    {"text": "focused.", "start": 0.4, "end": 1.0},
]


@pytest.fixture
def stub_front(tmp_path, monkeypatch):
    """Point the project dir at tmp and stub TTS + transcription."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(tts, "synthesize", lambda script, path: path)
    monkeypatch.setattr(transcribe, "transcribe_words", lambda path: MOCK_WORDS)


def test_moviepy_engine_selected(stub_front, monkeypatch):
    monkeypatch.setattr(settings, "caption_engine", "moviepy")
    monkeypatch.setattr(compose, "pick_background", lambda d: "/bg/clip.mp4")
    monkeypatch.setattr(compose, "compose_video", lambda **k: pytest.fail("ass path must not run"))

    seen = {}

    def fake_render(timeline, **kwargs):
        seen["timeline"] = timeline
        seen["kwargs"] = kwargs
        return kwargs["output_path"]

    monkeypatch.setattr(captions_moviepy, "render_reel", fake_render)

    out = pipeline.render_reel(1, "Stay focused.")
    assert out.name == "reel.mp4"
    assert seen["kwargs"]["background_path"] == "/bg/clip.mp4"
    # the pure timeline was built and handed to the renderer
    assert seen["timeline"]["chunks"][0]["words"][0]["text"] == "Stay"
    # timeline JSON persisted alongside the project
    assert (out.parent / "captions.json").exists()


def test_ass_engine_selected(stub_front, monkeypatch):
    monkeypatch.setattr(settings, "caption_engine", "ass")
    monkeypatch.setattr(
        captions_moviepy, "render_reel", lambda *a, **k: pytest.fail("moviepy must not run")
    )

    seen = {}
    monkeypatch.setattr(compose, "compose_video", lambda **k: seen.update(k) or k["output_path"])

    out = pipeline.render_reel(2, "Stay focused.")
    assert out.name == "reel.mp4"
    assert seen["ass_path"].name == "captions.ass"
    assert seen["ass_path"].exists()  # subtitles.write_ass actually ran


def test_unknown_engine_raises(stub_front, monkeypatch):
    monkeypatch.setattr(settings, "caption_engine", "bogus")
    with pytest.raises(captions.CaptionError):
        pipeline.render_reel(3, "Stay focused.")
