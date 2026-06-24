"""Offline sanity assertions for the FFmpeg argv builder and bg selection."""
from __future__ import annotations

import random

import pytest

from app.services import compose


def test_build_ffmpeg_cmd_shape():
    cmd = compose.build_ffmpeg_cmd(
        background_path="/bg/clip.mp4",
        audio_path="/work/narration.mp3",
        ass_path="/work/captions.ass",
        output_path="/work/reel.mp4",
    )
    assert cmd[0] == "ffmpeg"
    # background loops, both inputs mapped
    assert "-stream_loop" in cmd and "-1" in cmd
    assert cmd.count("-i") == 2
    assert "-shortest" in cmd
    # compact h264/aac encode
    assert "libx264" in cmd
    assert "aac" in cmd
    assert "yuv420p" in cmd
    # the .ass is burned via the subtitles filter inside -vf
    vf_index = cmd.index("-vf") + 1
    assert "subtitles=" in cmd[vf_index]
    assert cmd[-1] == "/work/reel.mp4"


def test_no_shell_injection_surface():
    # Args are a list (argv), never a single shell string.
    cmd = compose.build_ffmpeg_cmd(
        background_path="/bg/a b.mp4",
        audio_path="/work/n.mp3",
        ass_path="/work/c.ass",
        output_path="/work/o.mp4",
    )
    assert isinstance(cmd, list)
    assert all(isinstance(a, str) for a in cmd)


def test_subtitles_path_escaping():
    escaped = compose._escape_subtitles_path("/data/p:1/captions.ass")
    assert "\\:" in escaped  # colon escaped for the filtergraph parser


def test_pick_background_empty_raises(tmp_path):
    with pytest.raises(compose.CompositionError):
        compose.pick_background(tmp_path)


def test_pick_background_deterministic(tmp_path):
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (tmp_path / name).write_bytes(b"\x00")
    chosen = compose.pick_background(tmp_path, rng=random.Random(42))
    assert chosen.name in {"a.mp4", "b.mp4", "c.mp4"}
    assert chosen.exists()
