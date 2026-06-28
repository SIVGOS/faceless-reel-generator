"""Environment-driven application settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the `app` package.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets / external services
    gemini_api_key: str = ""
    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # Media
    tts_voice: str = "en-US-ChristopherNeural"
    whisper_model: str = "base"
    # Larger model auto-selected when the script contains Devanagari (Hindi /
    # Sanskrit). `base` aligns Devanagari poorly — a spoken Sanskrit verse yielded
    # zero words — so English reels keep `whisper_model` and Devanagari reels use
    # this one (heavier first-load + RAM, much better Devanagari word timings).
    whisper_model_devanagari: str = "small"

    # Voice engine (v2). `gemini` = native Gemini TTS (quality), `edge` = the free
    # edge-tts fallback. The Gemini path reuses GEMINI_API_KEY + google-genai SDK.
    tts_provider: str = "gemini"  # gemini | edge
    tts_gemini_model: str = "gemini-3.1-flash-tts-preview"
    tts_gemini_voice: str = "Kore"
    tts_style_prompt: str = (
        "Read as a warm, confident, upbeat narrator for a short vertical video. "
        "Natural pacing, clear articulation, light energy — not robotic."
    )
    # If the Gemini TTS path fails (quota, region, transient), auto-fall back to
    # the free edge-tts provider so a render still completes.
    tts_fallback_to_edge: bool = True

    # Used when the script contains Devanagari (Hindi / Sanskrit). The Gemini voice
    # timbre (tts_gemini_voice) is unchanged — accent comes from the text language
    # + this director prompt: authentic Devanagari pronunciation, neutral Indian
    # English on the rest, so the whole narration is one Indian narrator.
    tts_style_prompt_indian: str = (
        "You are narrating a short vertical video that mixes English with Hindi or "
        "Sanskrit written in Devanagari. Pronounce every Devanagari (Hindi / "
        "Sanskrit) word authentically and correctly — proper vowel length, "
        "anusvara, and conjunct consonants. Speak the English portions in a clear, "
        "neutral Indian English accent so the whole narration sounds like a single "
        "Indian narrator. Natural pacing, light energy — not robotic."
    )
    # edge-tts fallback voice for Devanagari content — an Indian voice that reads
    # both Devanagari and Latin (plain en-US mangles Hindi/Sanskrit).
    tts_voice_indian: str = "hi-IN-MadhurNeural"

    # Caption engine (v2): `moviepy` (animated, default), `ass` (light fallback),
    # `remotion` (documented future fallback, not built).
    caption_engine: str = "moviepy"
    # Display font for animated (moviepy) captions. Bundled OFL font lives under
    # app/assets/fonts and ships in the image (copied with the app package).
    caption_font_path: Path = BASE_DIR / "app" / "assets" / "fonts" / "Anton-Regular.ttf"
    # Devanagari caption font — applied PER WORD to Devanagari (Hindi / Sanskrit)
    # tokens while Latin words keep the Anton display font. Anton has no Devanagari
    # glyphs (would render tofu). Bundled OFL Noto, ships via `COPY app`.
    caption_font_devanagari_path: Path = (
        BASE_DIR / "app" / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"
    )
    # Frame rate for the moviepy render. 30 balances smoothness vs CPU cost.
    caption_fps: int = 30

    # Hard cap (seconds) for a single render job's subprocess work.
    render_timeout_seconds: int = 900

    # Gemini models (env-driven). Generation model is used for script writing;
    # embedding model is wired through config for future semantic features.
    gemini_generation_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    # First admin bootstrapped on startup (see auth gate, checkpoint G). Empty =
    # no auto-promotion. Lowercased for comparison against stored emails.
    admin_email: str = ""

    # Paths
    data_dir: Path = BASE_DIR / "data"
    # Background video library lives OUTSIDE the repo so large media files are
    # never committed. Point BG_VIDEO_FOLDER_PATH at any local/mounted folder of
    # .mp4 loops; falls back to ./backgrounds for local convenience.
    backgrounds_dir: Path = Field(
        default=BASE_DIR / "backgrounds",
        validation_alias="BG_VIDEO_FOLDER_PATH",
    )
    # Background-music library — mirrors backgrounds_dir exactly: lives OUTSIDE
    # the repo, mounted read-only, refreshable without a rebuild. Falls back to
    # ./music for local convenience.
    music_dir: Path = Field(
        default=BASE_DIR / "music",
        validation_alias="MUSIC_FOLDER_PATH",
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def session_cookie(self) -> str:
        return "reel_session"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Ensure runtime directories the app OWNS exist. The background library
    # (backgrounds_dir / BG_VIDEO_FOLDER_PATH) is external, possibly read-only
    # input — never auto-create it; pick_background() surfaces a clear error if
    # it is missing or empty.
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
