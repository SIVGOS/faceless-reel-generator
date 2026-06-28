"""Pure language / script detection for the reel pipeline.

Hindi and Sanskrit are written in **Devanagari**. The presence of Devanagari in a
script drives three downstream choices, all keyed off this one module:

- **TTS** — an Indian-accent style prompt + fallback voice so Devanagari is
  pronounced authentically and the English parts sound like one Indian narrator
  (see ``tts.py``).
- **Alignment** — a larger faster-whisper model + a Hindi language hint, because
  ``base`` with no hint produced zero words for spoken Sanskrit (see
  ``transcribe.py``).
- **Captions** — a Devanagari-capable font *per word*, since the Latin display
  font (Anton) renders Devanagari as tofu (see ``captions_moviepy.py``).

Detection is always on, so an otherwise-English reel that embeds a Sanskrit
shloka is handled too. Like ``subtitles.py`` / ``captions.py`` this imports
nothing heavy — it is covered by offline sanity tests.
"""
from __future__ import annotations

# Selectable script-generation languages: the UI picker values, the persisted
# `projects.language` column, and what Gemini is instructed to write in.
LANG_AUTO = "auto"
LANG_ENGLISH = "english"
LANG_HINDI = "hindi"
LANG_SANSKRIT = "sanskrit"
GENERATION_LANGUAGES = (LANG_AUTO, LANG_ENGLISH, LANG_HINDI, LANG_SANSKRIT)

# Whisper language hint for any Devanagari content. Hindi covers the script for
# alignment; Sanskrit alignment also benefits from the 'hi' hint over auto-detect.
DEVANAGARI_WHISPER_LANGUAGE = "hi"

# Unicode blocks carrying Devanagari + the Vedic accents used in Sanskrit.
_DEVANAGARI_RANGES = (
    (0x0900, 0x097F),  # Devanagari (base; includes the vedic tone marks)
    (0xA8E0, 0xA8FF),  # Devanagari Extended
    (0x1CD0, 0x1CFF),  # Vedic Extensions (Sanskrit)
)


def _is_devanagari_char(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in _DEVANAGARI_RANGES)


def contains_devanagari(text: str) -> bool:
    """True if any character of ``text`` is in a Devanagari / Vedic block."""
    return any(_is_devanagari_char(c) for c in (text or ""))


def is_devanagari_word(text: str) -> bool:
    """True if a caption token should render with the Devanagari font.

    A token counts as Devanagari if it carries any Devanagari letter — matras and
    the virama attach to such tokens, so even a mixed token (e.g. a trailing
    digit) must shape with the Devanagari font, not Anton.
    """
    return contains_devanagari(text)


def normalize_language(value: str | None) -> str:
    """Coerce a requested generation language to a known value (default ``auto``)."""
    v = (value or "").strip().lower()
    return v if v in GENERATION_LANGUAGES else LANG_AUTO
