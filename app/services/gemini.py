"""Gemini script generation. The google-genai SDK is imported lazily."""
from __future__ import annotations

from ..config import settings
from .language import (
    LANG_AUTO,
    LANG_ENGLISH,
    LANG_HINDI,
    LANG_SANSKRIT,
    normalize_language,
)

_BASE_INSTRUCTION = (
    "You are a professional shorts writer. Write a highly engaging, punchy, "
    "30-45 second script optimized for dynamic narration. Output ONLY the "
    "spoken text. Do not include scene descriptions, action notes, or "
    "parenthesis."
)

# Appended to the base instruction per chosen generation language. Hindi/Sanskrit
# MUST be Devanagari (never romanized) so the TTS and Devanagari captions engage.
_LANGUAGE_DIRECTIVE = {
    LANG_ENGLISH: "Write the script in English.",
    LANG_HINDI: (
        "Write the entire script in Hindi using DEVANAGARI script (देवनागरी). "
        "Never romanize Hindi (no Hinglish / Latin spelling of Hindi words). A few "
        "widely-understood English words are acceptable only if they read naturally."
    ),
    LANG_SANSKRIT: (
        "Compose the script in Sanskrit using DEVANAGARI script (देवनागरी), with "
        "correct sandhi and verse form where it fits. A brief explanation may be in "
        "simple Hindi (also Devanagari) or English, but never romanize any Sanskrit "
        "or Hindi."
    ),
    LANG_AUTO: (
        "Write in English by default. If the user's prompt is itself written in "
        "Hindi or Sanskrit (Devanagari), respond in that same language using "
        "Devanagari script — never romanized."
    ),
}

# Back-compat alias (default/auto instruction) for any external reference.
SYSTEM_INSTRUCTION = f"{_BASE_INSTRUCTION}\n\n{_LANGUAGE_DIRECTIVE[LANG_AUTO]}"


def _system_instruction(language: str) -> str:
    directive = _LANGUAGE_DIRECTIVE.get(language, _LANGUAGE_DIRECTIVE[LANG_AUTO])
    return f"{_BASE_INSTRUCTION}\n\n{directive}"


class ScriptGenerationError(RuntimeError):
    pass


def generate_script(prompt: str, language: str = LANG_AUTO) -> str:
    """Call the generation model and return clean spoken-text only.

    ``language`` (auto | english | hindi | sanskrit) selects the script language;
    hindi/sanskrit are written in Devanagari so the rest of the pipeline (Indian
    TTS, Devanagari captions) engages. Raises ScriptGenerationError if the API key
    is missing or the call fails.
    """
    language = normalize_language(language)

    if not settings.gemini_api_key:
        raise ScriptGenerationError(
            "GEMINI_API_KEY is not configured. Set it in .env."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on install
        raise ScriptGenerationError(
            "google-genai is not installed. `pip install google-genai`."
        ) from exc

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_generation_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_system_instruction(language),
                temperature=0.9,
            ),
        )
    except Exception as exc:  # SDK raises a variety of error types
        raise ScriptGenerationError(f"Gemini request failed: {exc}") from exc

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ScriptGenerationError("Gemini returned an empty script.")
    return text
