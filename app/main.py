"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import auth, projects

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Faceless Reel Generator", lifespan=lifespan)


@app.middleware("http")
async def no_cache_app_shell(request, call_next):
    """Force revalidation of the SPA shell so a redeploy can't serve stale HTML/JS.

    Scoped to `/` and `/static/*` only — API responses and video range requests
    keep their normal caching.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "voice": settings.tts_voice,
        "model": settings.gemini_generation_model,
        "embedding_model": settings.gemini_embedding_model,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Serve CSS/JS assets.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
