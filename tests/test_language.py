"""Offline sanity assertions for the pure language / script detection module."""
from __future__ import annotations

from app.services import language as lang


# --------------------------------------------------------------------------- #
# Devanagari detection
# --------------------------------------------------------------------------- #
def test_contains_devanagari_pure_english():
    assert lang.contains_devanagari("Resilience is forged in fire.") is False
    assert lang.contains_devanagari("") is False
    assert lang.contains_devanagari(None) is False


def test_contains_devanagari_hindi_and_sanskrit():
    assert lang.contains_devanagari("अलसस्य कुतो विद्या") is True  # Sanskrit verse
    assert lang.contains_devanagari("जीवन एक यात्रा है") is True  # Hindi


def test_contains_devanagari_mixed_script():
    # An English reel that embeds a shloka must still be flagged.
    assert lang.contains_devanagari("This verse, अलसस्य, means…") is True


def test_is_devanagari_word_per_token():
    assert lang.is_devanagari_word("विद्या") is True
    assert lang.is_devanagari_word("knowledge") is False
    # A Devanagari token with attached matra/virama still counts.
    assert lang.is_devanagari_word("कुतो,") is True


# --------------------------------------------------------------------------- #
# Generation-language normalization
# --------------------------------------------------------------------------- #
def test_normalize_language_known_values():
    assert lang.normalize_language("Hindi") == lang.LANG_HINDI
    assert lang.normalize_language("  SANSKRIT ") == lang.LANG_SANSKRIT
    assert lang.normalize_language("english") == lang.LANG_ENGLISH
    assert lang.normalize_language("auto") == lang.LANG_AUTO


def test_normalize_language_unknown_defaults_to_auto():
    assert lang.normalize_language("klingon") == lang.LANG_AUTO
    assert lang.normalize_language("") == lang.LANG_AUTO
    assert lang.normalize_language(None) == lang.LANG_AUTO
