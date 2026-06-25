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

    # Caption engine (v2): `moviepy` (animated, default), `ass` (light fallback),
    # `remotion` (documented future fallback, not built).
    caption_engine: str = "moviepy"

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
