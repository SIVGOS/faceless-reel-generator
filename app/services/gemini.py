"""Gemini script generation. The google-genai SDK is imported lazily."""
from __future__ import annotations

from ..config import settings

SYSTEM_INSTRUCTION = (
    "You are a professional shorts writer. Write a highly engaging, punchy, "
    "30-45 second script optimized for dynamic narration. Output ONLY the "
    "spoken text. Do not include scene descriptions, action notes, or "
    "parenthesis."
)


class ScriptGenerationError(RuntimeError):
    pass


def generate_script(prompt: str) -> str:
    """Call gemini-2.5-flash and return clean spoken-text only.

    Raises ScriptGenerationError if the API key is missing or the call fails.
    """
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
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.9,
            ),
        )
    except Exception as exc:  # SDK raises a variety of error types
        raise ScriptGenerationError(f"Gemini request failed: {exc}") from exc

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ScriptGenerationError("Gemini returned an empty script.")
    return text
