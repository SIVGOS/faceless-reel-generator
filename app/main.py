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

app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "voice": settings.tts_voice, "model": settings.gemini_model}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Serve CSS/JS assets.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
