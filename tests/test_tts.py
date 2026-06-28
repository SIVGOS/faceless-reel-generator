"""Offline sanity assertions for the TTS provider seam and pure helpers.

No network and no SDK calls: the Gemini request and edge synth are monkeypatched,
the PCM->WAV decode runs on a fixture buffer, and the loudnorm argv is pure.
"""
from __future__ import annotations

import struct
import wave

import pytest

from app.config import settings
from app.services import tts


# --------------------------------------------------------------------------- #
# Provider dispatch
# --------------------------------------------------------------------------- #
def test_dispatch_edge(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "edge")
    calls = {}

    def rec_edge(t, o, v):
        calls["edge"] = (t, o, v)
        return "edge.mp3"

    monkeypatch.setattr(tts, "_synthesize_edge", rec_edge)
    monkeypatch.setattr(tts, "_synthesize_gemini", lambda *a, **k: pytest.fail("gemini should not run"))
    assert tts.synthesize("hi", "/work/n.mp3") == "edge.mp3"
    assert calls["edge"] == ("hi", "/work/n.mp3", None)


def test_dispatch_gemini(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "gemini")
    monkeypatch.setattr(tts, "_synthesize_gemini", lambda t, o, v: "gemini.wav")
    monkeypatch.setattr(tts, "_synthesize_edge", lambda *a, **k: pytest.fail("edge should not run"))
    assert tts.synthesize("hi", "/work/n.mp3") == "gemini.wav"


def test_dispatch_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "bogus")
    with pytest.raises(tts.TTSError):
        tts.synthesize("hi", "/work/n.mp3")


def test_gemini_failure_falls_back_to_edge(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "gemini")
    monkeypatch.setattr(settings, "tts_fallback_to_edge", True)

    def boom(*a, **k):
        raise tts.TTSError("quota exceeded")

    fell_back = {}

    def rec_edge(t, o, v):
        fell_back["v"] = v
        return "edge.mp3"

    monkeypatch.setattr(tts, "_synthesize_gemini", boom)
    monkeypatch.setattr(tts, "_synthesize_edge", rec_edge)

    assert tts.synthesize("hi", "/work/n.mp3") == "edge.mp3"
    # fallback hands edge None (the failed `voice` was a Gemini voice name).
    assert fell_back["v"] is None


def test_gemini_failure_reraises_when_fallback_disabled(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "gemini")
    monkeypatch.setattr(settings, "tts_fallback_to_edge", False)
    monkeypatch.setattr(tts, "_synthesize_gemini", lambda *a, **k: (_ for _ in ()).throw(tts.TTSError("x")))
    monkeypatch.setattr(tts, "_synthesize_edge", lambda *a, **k: pytest.fail("must not fall back"))
    with pytest.raises(tts.TTSError):
        tts.synthesize("hi", "/work/n.mp3")


# --------------------------------------------------------------------------- #
# PCM -> WAV decode (pure, stdlib)
# --------------------------------------------------------------------------- #
def test_pcm_to_wav_roundtrip(tmp_path):
    # 100 mono 16-bit samples.
    samples = [((-1) ** i) * (i * 37 % 1000) for i in range(100)]
    pcm = struct.pack("<%dh" % len(samples), *samples)
    wav_path = tmp_path / "a.wav"

    out = tts.pcm_to_wav(pcm, wav_path)
    assert out == wav_path and out.exists()

    with wave.open(str(wav_path), "rb") as w:
        assert w.getnchannels() == tts.GEMINI_TTS_CHANNELS
        assert w.getsampwidth() == tts.GEMINI_TTS_SAMPLE_WIDTH
        assert w.getframerate() == tts.GEMINI_TTS_SAMPLE_RATE
        assert w.getnframes() == len(samples)
        assert w.readframes(len(samples)) == pcm


# --------------------------------------------------------------------------- #
# loudnorm argv builder (pure)
# --------------------------------------------------------------------------- #
def test_build_loudnorm_cmd_shape():
    cmd = tts.build_loudnorm_cmd("/work/n.raw.wav", "/work/n.wav")
    assert cmd[0] == "ffmpeg"
    assert isinstance(cmd, list) and all(isinstance(a, str) for a in cmd)
    af_index = cmd.index("-af") + 1
    assert cmd[af_index].startswith("loudnorm=")
    assert "pcm_s16le" in cmd
    assert str(tts.GEMINI_TTS_SAMPLE_RATE) in cmd
    assert cmd[-1] == "/work/n.wav"
    assert cmd.count("-i") == 1


# --------------------------------------------------------------------------- #
# PCM extraction from a mocked SDK response
# --------------------------------------------------------------------------- #
class _Inline:
    def __init__(self, data):
        self.data = data


class _Part:
    def __init__(self, data):
        self.inline_data = _Inline(data)


class _Resp:
    def __init__(self, parts):
        self.candidates = [type("C", (), {"content": type("Co", (), {"parts": parts})()})()]


def test_extract_pcm_finds_inline_data():
    assert tts._extract_pcm(_Resp([_Part(b"\x01\x02")])) == b"\x01\x02"


def test_extract_pcm_empty_when_no_parts():
    assert tts._extract_pcm(_Resp([])) == b""
    assert tts._extract_pcm(object()) == b""


# --------------------------------------------------------------------------- #
# Indian-accent selection on Devanagari content
# --------------------------------------------------------------------------- #
def _fake_edge_tts(monkeypatch, captured):
    """Inject a fake edge_tts module that records the voice it is given."""
    import sys
    import types as pytypes

    fake = pytypes.ModuleType("edge_tts")

    class Communicate:
        def __init__(self, text, voice):
            captured["voice"] = voice

        async def save(self, path):
            from pathlib import Path

            Path(path).write_bytes(b"\x00\x01")  # non-empty so the guard passes

    fake.Communicate = Communicate
    monkeypatch.setitem(sys.modules, "edge_tts", fake)


def test_edge_uses_indian_voice_for_devanagari(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "tts_voice", "en-US-ChristopherNeural")
    monkeypatch.setattr(settings, "tts_voice_indian", "hi-IN-MadhurNeural")
    captured = {}
    _fake_edge_tts(monkeypatch, captured)

    tts._synthesize_edge("अलसस्य कुतो विद्या", tmp_path / "n.mp3", None)
    assert captured["voice"] == "hi-IN-MadhurNeural"


def test_edge_uses_default_voice_for_english(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "tts_voice", "en-US-ChristopherNeural")
    monkeypatch.setattr(settings, "tts_voice_indian", "hi-IN-MadhurNeural")
    captured = {}
    _fake_edge_tts(monkeypatch, captured)

    tts._synthesize_edge("Stay focused.", tmp_path / "n.mp3", None)
    assert captured["voice"] == "en-US-ChristopherNeural"


def test_edge_explicit_voice_overrides_detection(monkeypatch, tmp_path):
    captured = {}
    _fake_edge_tts(monkeypatch, captured)
    tts._synthesize_edge("अलसस्य", tmp_path / "n.mp3", "custom-voice")
    assert captured["voice"] == "custom-voice"
