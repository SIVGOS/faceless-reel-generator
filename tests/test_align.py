"""Offline sanity assertions for the pure script↔timing alignment.

Captions must show the EXACT script text with whisper-derived timing, even when
whisper mis-spells the audio (especially Devanagari). No heavy deps here.
"""
from __future__ import annotations

from app.services import align


# --------------------------------------------------------------------------- #
# Phonetic normalisation
# --------------------------------------------------------------------------- #
def test_normalize_folds_devanagari_confusions():
    # whisper drops aspiration (ध→द) and merges sibilants (ष→स): exact fold.
    assert align.normalize_for_match("धन") == align.normalize_for_match("दन")
    assert align.normalize_for_match("ष") == align.normalize_for_match("स")
    # anusvara vs conjunct-nasal (संसार vs whisper's सन्सार) doesn't fully collapse
    # but stays highly similar, so the aligner still matches the pair.
    a = align.normalize_for_match("संसार")
    b = align.normalize_for_match("सन्सार")
    assert align._similarity(a, b) >= 0.75


def test_normalize_strips_punctuation_and_case():
    assert align.normalize_for_match("Fire.") == "fire"
    assert align.normalize_for_match("धनम्।") == align.normalize_for_match("धनम")


# --------------------------------------------------------------------------- #
# Core alignment
# --------------------------------------------------------------------------- #
def test_exact_english_inherits_timing():
    whisper = [
        {"text": "Stay", "start": 0.0, "end": 0.4},
        {"text": "focused.", "start": 0.4, "end": 1.0},
    ]
    out = align.align_script_to_timings("Stay focused.", whisper)
    assert [w["text"] for w in out] == ["Stay", "focused."]
    assert out[0]["start"] == 0.0 and out[1]["end"] == 1.0


def test_misspelled_devanagari_keeps_script_text_not_whisper():
    # whisper garbled the text; timing is still usable.
    whisper = [
        {"text": "दन", "start": 0.0, "end": 0.5},          # should be धन
        {"text": "सन्सार", "start": 0.5, "end": 1.2},       # should be संसार
    ]
    out = align.align_script_to_timings("धन संसार", whisper)
    # caption TEXT is the script, never whisper's spelling
    assert [w["text"] for w in out] == ["धन", "संसार"]
    # but the timing came from the (phonetically-matched) whisper words
    assert out[0]["start"] == 0.0
    assert out[1]["end"] == 1.2


def test_more_script_words_than_whisper_interpolates():
    # whisper merged/missed words: every script word still gets a timing.
    whisper = [{"text": "अलसस्य", "start": 0.0, "end": 1.0}]
    out = align.align_script_to_timings("अलसस्य कुतो विद्या", whisper)
    assert [w["text"] for w in out] == ["अलसस्य", "कुतो", "विद्या"]
    times = [(w["start"], w["end"]) for w in out]
    # monotonic, non-degenerate
    for s, e in times:
        assert e >= s
    assert times == sorted(times)


def test_extra_whisper_words_are_dropped():
    # whisper split one word into two; script text wins, timing spans sensibly.
    whisper = [
        {"text": "vid", "start": 0.0, "end": 0.3},
        {"text": "ya", "start": 0.3, "end": 0.7},
        {"text": "knowledge", "start": 0.7, "end": 1.4},
    ]
    out = align.align_script_to_timings("knowledge", whisper)
    assert [w["text"] for w in out] == ["knowledge"]
    assert out[0]["end"] == 1.4


def test_leading_junk_tokens_are_filtered_no_time_shift():
    # whisper emits diacritic-only junk at the start ("॑", "ृ") with early times;
    # they must be dropped so the first real script word keeps its early timing
    # instead of anchoring to a later, more-similar whisper token.
    whisper = [
        {"text": "॑", "start": 0.0, "end": 0.4},     # junk
        {"text": "ृ", "start": 0.4, "end": 0.5},      # junk
        {"text": "अलसस्य", "start": 0.5, "end": 1.2},  # real first word
        {"text": "कुतो", "start": 1.2, "end": 1.6},
    ]
    out = align.align_script_to_timings("अलसस्य कुतो", whisper)
    assert [w["text"] for w in out] == ["अलसस्य", "कुतो"]
    assert out[0]["start"] == 0.5  # not shifted off the junk timestamps


def test_empty_inputs_return_empty_for_fallback():
    assert align.align_script_to_timings("", [{"text": "x", "start": 0, "end": 1}]) == []
    assert align.align_script_to_timings("hello", []) == []
