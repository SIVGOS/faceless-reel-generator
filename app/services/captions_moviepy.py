"""MoviePy renderer for the caption timeline (the chosen v2 caption engine).

Consumes the engine-agnostic timeline from ``captions.build_timeline`` and
renders the full reel: background video (cover-fit + looped to the narration)
with an animated, word-by-word caption layer composited on top, narration as the
audio track.

Per-word animation (hand-rolled easing of clip-local time ``t``):
- **pop-in:** every word in a chunk scales up from ~0 with an ease-out-back
  overshoot, lightly staggered across the chunk for a cascade.
- **active highlight:** while a word is being spoken, an accent-coloured copy
  scaled up slightly overlays the white base word.

The easing helpers at module top are pure (no MoviePy) and unit-tested. MoviePy
itself is imported lazily inside ``render_reel`` so this module — and the easing
tests — import without the heavy dependency. The render runs behind the async
job boundary (checkpoint B).
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from .captions import CaptionError
from .language import is_devanagari_word

# --- Layout / style (authored against the 1080x1920 timeline frame) --------- #
DEFAULT_FONT_SIZE = 92
VERTICAL_CENTER_FRACTION = 0.72  # caption band sits in the lower third
WORD_SPACE_FRACTION = 0.32       # inter-word gap as a fraction of font size
STROKE_WIDTH = 8

BASE_COLOR = "white"
ACCENT_COLOR = "#FFE600"  # vivid yellow for the active / emphasised word
STROKE_COLOR = "black"

# --- Animation timing ------------------------------------------------------- #
POP_DURATION = 0.18   # seconds for a word to pop to full size
POP_STAGGER = 0.05    # per-word delay within a chunk (cascade)
POP_MIN_SCALE = 0.06  # never scale to exactly 0 (zero-size frames error)
ACTIVE_SCALE = 1.12   # how much the spoken word grows
EMPHASIS_SCALE = 1.18  # emphasised words grow a touch more when active


# --------------------------------------------------------------------------- #
# Pure easing helpers (no MoviePy — unit-tested)
# --------------------------------------------------------------------------- #
def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def ease_out_back(p: float, overshoot: float = 1.70158) -> float:
    """Ease-out with a slight overshoot past 1.0. Maps p:0->0, 1->1."""
    p = clamp01(p)
    p1 = p - 1.0
    return 1.0 + (overshoot + 1.0) * p1 ** 3 + overshoot * p1 ** 2


def pop_scale(t: float, duration: float = POP_DURATION) -> float:
    """Scale factor for a popping-in word at clip-local time ``t`` seconds."""
    if duration <= 0 or t >= duration:
        return 1.0
    if t <= 0:
        return POP_MIN_SCALE
    return max(POP_MIN_SCALE, ease_out_back(t / duration))


def font_for_word(text: str, latin_font: str, devanagari_font: str) -> str:
    """Pick the font for one caption token by its script.

    Devanagari (Hindi / Sanskrit) words need a Devanagari-capable font; the Latin
    display font (Anton) would render them as tofu. Latin words keep Anton.
    """
    return devanagari_font if is_devanagari_word(text) else latin_font


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render_reel(
    timeline: dict,
    *,
    background_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    font_path: str | Path | None = None,
    font_path_devanagari: str | Path | None = None,
    font_size: int = DEFAULT_FONT_SIZE,
    fps: int | None = None,
) -> Path:
    """Render the timeline to a 9:16 reel mp4. Returns the output path.

    Raises CaptionError on any MoviePy/encode failure so the render job can
    record it (mirrors CompositionError on the ffmpeg path).
    """
    try:
        from moviepy import (
            AudioFileClip,
            CompositeVideoClip,
            TextClip,
            VideoFileClip,
            vfx,
        )
    except ImportError as exc:  # pragma: no cover - depends on install
        raise CaptionError(
            "moviepy is not installed. `pip install moviepy` (bundled in Docker)."
        ) from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_path = str(font_path or settings.caption_font_path)
    font_path_devanagari = str(
        font_path_devanagari or settings.caption_font_devanagari_path
    )
    fps = fps or settings.caption_fps

    frame = timeline.get("frame") or {}
    W = int(frame.get("width", 1080))
    H = int(frame.get("height", 1920))
    y_center = H * VERTICAL_CENTER_FRACTION
    space = int(font_size * WORD_SPACE_FRACTION)

    audio = bg = comp = None
    try:
        audio = AudioFileClip(str(audio_path))
        duration = float(audio.duration)

        # Background: cover-fit (scale to fill, centre-crop) + loop to length.
        bg = VideoFileClip(str(background_path)).without_audio()
        scale = max(W / bg.w, H / bg.h)
        bg = bg.resized(scale)
        bg = bg.cropped(x_center=bg.w / 2, y_center=bg.h / 2, width=W, height=H)
        bg = bg.with_effects([vfx.Loop(duration=duration)]).with_duration(duration)

        def make_text(text: str, color: str):
            return TextClip(
                font=font_for_word(text, font_path, font_path_devanagari),
                text=text,
                font_size=font_size,
                color=color,
                stroke_color=STROKE_COLOR,
                stroke_width=STROKE_WIDTH,
                method="label",
            )

        word_layers = []
        for chunk in timeline.get("chunks", []):
            word_layers.extend(
                _build_chunk_clips(chunk, make_text, W=W, y_center=y_center, space=space)
            )

        comp = CompositeVideoClip([bg, *word_layers], size=(W, H)).with_duration(duration)
        comp = comp.with_audio(audio)

        comp.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            temp_audiofile=str(output_path.with_suffix(".temp-audio.m4a")),
            remove_temp=True,
            logger=None,
        )
    except CaptionError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any MoviePy/encode failure
        raise CaptionError(f"MoviePy render failed: {exc}") from exc
    finally:
        for clip in (comp, bg, audio):
            try:
                if clip is not None:
                    clip.close()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise CaptionError("MoviePy reported success but no output file was written.")
    return output_path


def _build_chunk_clips(chunk: dict, make_text, *, W: int, y_center: float, space: int):
    """Build the base + active TextClips for one on-screen chunk."""
    words = chunk.get("words", [])
    if not words:
        return []

    # Measure each word, then centre the group horizontally.
    bases = [make_text(w["text"], BASE_COLOR) for w in words]
    widths = [b.w for b in bases]
    total = sum(widths) + space * (len(words) - 1)
    x = (W - total) / 2.0

    chunk_start = float(chunk["start"])
    chunk_end = float(chunk["end"])
    layers = []

    for i, (w, base) in enumerate(zip(words, bases)):
        cw, ch = base.w, base.h
        cx = x + cw / 2.0           # word centre x
        cy = y_center               # word centre y
        x += cw + space

        # --- base white word: appears at chunk start (staggered), pops in ---
        appear = chunk_start + i * POP_STAGGER
        base = (
            base.with_start(appear)
            .with_duration(max(0.05, chunk_end - appear))
            .resized(lambda t: pop_scale(t))
            .with_position(_centered_position(cx, cy, cw, ch, scale_fn=pop_scale))
        )
        layers.append(base)

        # --- accent overlay while the word is spoken ---
        w_start = float(w["start"])
        w_end = float(w["end"])
        if w_end > w_start:
            grow = EMPHASIS_SCALE if w.get("emphasis") else ACTIVE_SCALE
            active = make_text(w["text"], ACCENT_COLOR)
            active = (
                active.with_start(w_start)
                .with_duration(w_end - w_start)
                .resized(grow)
                .with_position((cx - cw * grow / 2.0, cy - ch * grow / 2.0))
            )
            layers.append(active)

    return layers


def _centered_position(cx: float, cy: float, w: float, h: float, *, scale_fn):
    """A position(t) that keeps a clip centred on (cx, cy) as it scales."""
    def position(t):
        s = scale_fn(t)
        return (cx - w * s / 2.0, cy - h * s / 2.0)

    return position
