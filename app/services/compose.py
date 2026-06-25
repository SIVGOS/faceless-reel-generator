"""FFmpeg composition: stitch a random background loop + narration + captions.

The argv builder (`build_ffmpeg_cmd`) is pure and unit-tested. `compose_video`
runs it as an explicit, no-shell subprocess with a timeout and surfaces stderr.
"""
from __future__ import annotations

import random
import subprocess
from pathlib import Path

# Output encode targets: compact, broadly compatible vertical reel.
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FFMPEG_TIMEOUT_SECONDS = 600


class CompositionError(RuntimeError):
    """Raised when background selection or ffmpeg execution fails."""


def pick_background(backgrounds_dir: str | Path, rng: random.Random | None = None) -> Path:
    """Return a random .mp4 from the background pool."""
    backgrounds_dir = Path(backgrounds_dir)
    pool = sorted(backgrounds_dir.glob("*.mp4"))
    if not pool:
        raise CompositionError(
            f"No .mp4 background files found in {backgrounds_dir}. "
            "Mount at least one video into ./backgrounds."
        )
    chooser = rng or random
    return chooser.choice(pool)


def _escape_subtitles_path(path: str | Path) -> str:
    r"""Escape a path for use inside the ffmpeg subtitles= filter.

    The filtergraph parser treats ':' and '\' specially and the whole filter
    arg is single-quoted, so backslashes, colons and single quotes are escaped.
    """
    p = str(path)
    p = p.replace("\\", "\\\\")
    p = p.replace(":", "\\:")
    p = p.replace("'", "\\'")
    return p


def build_ffmpeg_cmd(
    *,
    background_path: str | Path,
    audio_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> list[str]:
    """Build the ffmpeg argv.

    - `-stream_loop -1` repeats the background so short clips still cover audio.
    - scale+crop forces a clean 9:16 frame regardless of source aspect.
    - `subtitles=` burns the karaoke .ass over the scaled video.
    - `-shortest` trims output to the narration length.
    - h264 (yuv420p) + aac for compact, universally playable output.
    """
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"subtitles='{_escape_subtitles_path(ass_path)}'"
    )
    return [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", str(background_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]


def compose_video(
    *,
    audio_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    backgrounds_dir: str | Path,
    background_path: str | Path | None = None,
    timeout_seconds: int = FFMPEG_TIMEOUT_SECONDS,
) -> Path:
    """Run the full composition and return the output path."""
    bg = Path(background_path) if background_path else pick_background(backgrounds_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = build_ffmpeg_cmd(
        background_path=bg,
        audio_path=audio_path,
        ass_path=ass_path,
        output_path=output_path,
    )
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing dependent
        raise CompositionError(f"ffmpeg timed out after {timeout_seconds}s") from exc

    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise CompositionError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")
    if not output_path.exists():
        raise CompositionError("ffmpeg reported success but no output file was written.")
    return output_path
