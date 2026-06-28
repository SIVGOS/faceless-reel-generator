"""Map reliable whisper word *timings* onto the known-correct script *text*.

Captions must show the exact script (correct spelling), but the only source of
per-word timing is faster-whisper — whose transcribed TEXT is unreliable for
Devanagari (and occasionally English). So we keep whisper's timestamps and throw
away its text: a monotonic (Needleman–Wunsch) alignment matches each script word
to the whisper word(s) spoken at the same moment, using a script-aware phonetic
normalisation so whisper's mis-spellings (dropped aspiration, श/ष→स, ण→न, stray
anusvara) still match their correct forms. Script words with no anchor get their
timing interpolated from neighbours.

The narration is the script read start-to-finish, so the alignment is monotonic
and anchors well. Pure / no heavy deps — covered by offline sanity tests; the
output feeds straight into ``captions.build_timeline``.
"""
from __future__ import annotations

import re

# All Devanagari combining marks: candrabindu/anusvara/visarga, nukta, every vowel
# matra, the virama, and the vedic stress accents. We match on the bare CONSONANT
# SKELETON — matras/accents/aspiration are exactly what whisper mis-hears, and a
# token that is *only* such marks (whisper junk like "॑" or "ृ") collapses to empty
# and is then filtered out before alignment.
_DEVA_COMBINING_RE = re.compile(
    r"[ऀ-ःऺ-़ा-ॏ॑-ॗॢॣ]"
)
# Base letters/digits/om to keep after combining marks are stripped (excludes the
# danda । / ॥ and all punctuation, which live just outside this set).
_DEVA_KEEP_RE = re.compile(r"[^0-9a-zऄ-हॐक़-ॡ०-९]+")

# Fold aspirated / sibilant / retroflex-nasal letters to a common base so the most
# common whisper Devanagari confusions still match (it tends to drop aspiration:
# ध→द, घ→ग; merge sibilants श/ष→स; and flatten ण→न).
_DEVA_FOLD = str.maketrans(
    {
        "ख": "क", "घ": "ग",   # kh→k, gh→g
        "छ": "च", "झ": "ज",   # ch→c, jh→j
        "ठ": "ट", "ढ": "ड",   # ṭh→ṭ, ḍh→ḍ
        "थ": "त", "ध": "द",   # th→t, dh→d
        "फ": "प", "भ": "ब",   # ph→p, bh→b
        "श": "स", "ष": "स",   # ś, ṣ → s
        "ण": "न",             # ṇ → n
    }
)

# No diagonal match can beat a pair of gaps below this; tuned so equal-length
# sequences stay all-diagonal and only genuine count mismatches open gaps.
GAP_PENALTY = -0.4

# Fallback per-word duration for trailing script words past the last anchor.
_DEFAULT_WORD_SECONDS = 0.3


def normalize_for_match(text: str) -> str:
    """Reduce a token to its bare consonant skeleton for fuzzy matching.

    Lowercases, removes all Devanagari combining marks (matras/virama/accents),
    folds aspirated/sibilant variants, and drops punctuation + danda. Diacritic-
    only whisper junk (e.g. "॑", "ृ") collapses to "" so it can be filtered out.
    """
    t = (text or "").strip().lower()
    t = _DEVA_COMBINING_RE.sub("", t)
    t = t.translate(_DEVA_FOLD)
    return _DEVA_KEEP_RE.sub("", t)


def _split_script(script_text: str) -> list[str]:
    """Whitespace-split into display tokens (punctuation/danda stays attached)."""
    return [tok for tok in re.split(r"\s+", (script_text or "").strip()) if tok]


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _similarity(a: str, b: str) -> float:
    """1.0 for identical normalised tokens, 0.0 for fully dissimilar."""
    m = max(len(a), len(b))
    if m == 0:
        return 1.0
    return 1.0 - _edit_distance(a, b) / m


def _traceback(bt: list[list[int]], M: int, N: int) -> dict[int, int]:
    """Walk backpointers; return {script_index: whisper_index} for diagonal pairs."""
    anchors: dict[int, int] = {}
    i, j = M, N
    while i > 0 and j > 0:
        move = bt[i][j]
        if move == 0:  # diagonal: S[i-1] aligned to W[j-1]
            anchors[i - 1] = j - 1
            i -= 1
            j -= 1
        elif move == 1:  # up: script token unaligned (gap in whisper)
            i -= 1
        else:  # left: whisper token unaligned (dropped)
            j -= 1
    return anchors


def align_script_to_timings(script_text: str, whisper_words: list[dict]) -> list[dict]:
    """Return script words as ``{text, start, end}`` with whisper-derived timing.

    ``whisper_words`` are ``{text|word, start, end}`` dicts (timing trusted, text
    discarded). Returns ``[]`` when there is nothing to align (no script tokens or
    no timed words) so the caller can fall back to the raw whisper words.
    """
    script_tokens = _split_script(script_text)
    # Keep only whisper words with a real skeleton — drops diacritic-only junk
    # ("॑", "ृ", "�") that whisper emits at boundaries and that would otherwise
    # mis-anchor the first real script word (shoving captions seconds late).
    timed = [
        w
        for w in (whisper_words or [])
        if normalize_for_match(w.get("text") or w.get("word") or "")
    ]
    if not script_tokens or not timed:
        return []

    M, N = len(script_tokens), len(timed)
    snorm = [normalize_for_match(t) for t in script_tokens]
    wnorm = [normalize_for_match(w.get("text") or w.get("word") or "") for w in timed]

    # Needleman–Wunsch with backpointers (0=diag, 1=up/script-gap, 2=left/whisper-gap).
    score = [[0.0] * (N + 1) for _ in range(M + 1)]
    bt = [[0] * (N + 1) for _ in range(M + 1)]
    for i in range(1, M + 1):
        score[i][0] = i * GAP_PENALTY
        bt[i][0] = 1
    for j in range(1, N + 1):
        score[0][j] = j * GAP_PENALTY
        bt[0][j] = 2
    for i in range(1, M + 1):
        for j in range(1, N + 1):
            diag = score[i - 1][j - 1] + _similarity(snorm[i - 1], wnorm[j - 1])
            up = score[i - 1][j] + GAP_PENALTY
            left = score[i][j - 1] + GAP_PENALTY
            best = max(diag, up, left)
            score[i][j] = best
            bt[i][j] = 0 if best == diag else (1 if best == up else 2)

    anchors = _traceback(bt, M, N)

    starts: list[float | None] = [None] * M
    ends: list[float | None] = [None] * M
    for i, j in anchors.items():
        starts[i] = float(timed[j]["start"])
        ends[i] = float(timed[j]["end"])

    _interpolate_gaps(starts, ends, timed)

    return [
        {"text": script_tokens[i], "start": float(starts[i]), "end": float(ends[i])}
        for i in range(M)
    ]


def _interpolate_gaps(
    starts: list[float | None], ends: list[float | None], timed: list[dict]
) -> None:
    """Fill un-anchored script words by spreading them across neighbouring time."""
    M = len(starts)
    anchored = [i for i in range(M) if starts[i] is not None]

    if not anchored:  # pathological: spread evenly across the whisper span
        t0 = float(timed[0]["start"])
        t1 = max(t0 + 0.1, float(timed[-1]["end"]))
        for k in range(M):
            starts[k] = t0 + (t1 - t0) * k / M
            ends[k] = t0 + (t1 - t0) * (k + 1) / M
        return

    # Leading gap: spread from just before the first anchor up to it.
    first = anchored[0]
    if first > 0:
        t1 = starts[first]
        t0 = max(0.0, t1 - _DEFAULT_WORD_SECONDS * first)
        _spread(starts, ends, 0, first, t0, t1)

    # Interior gaps: spread across the interval between the two flanking anchors.
    for a, b in zip(anchored, anchored[1:]):
        if b - a > 1:
            t0, t1 = ends[a], max(ends[a], starts[b])
            _spread(starts, ends, a + 1, b, t0, t1)

    # Trailing gap: extend past the last anchor at the default cadence.
    last = anchored[-1]
    if last < M - 1:
        t0 = ends[last]
        for m, k in enumerate(range(last + 1, M)):
            starts[k] = t0 + _DEFAULT_WORD_SECONDS * m
            ends[k] = t0 + _DEFAULT_WORD_SECONDS * (m + 1)


def _spread(
    starts: list[float | None],
    ends: list[float | None],
    lo: int,
    hi: int,
    t0: float,
    t1: float,
) -> None:
    """Evenly lay tokens [lo, hi) across [t0, t1)."""
    n = hi - lo
    if n <= 0:
        return
    step = (t1 - t0) / n
    for m, k in enumerate(range(lo, hi)):
        starts[k] = t0 + step * m
        ends[k] = t0 + step * (m + 1)
