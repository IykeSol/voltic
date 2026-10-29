"""Application entry point: wires routes, database and the static frontend."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

# Allow running this file directly (`python app/main.py`) by making the project
# root importable as the `app` package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai import gemini_client
from app.config import settings
from app.database.db import init_db, is_turso_configured, seed_if_empty
from app.routes import ai, auth, export, profile, usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_if_empty()
    print(f"[startup] {settings.PROJECT_NAME} ready. "
          f"Gemini: {'on' if gemini_client.is_available() else 'offline-fallback'}")
    yield


app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(usage.router)
app.include_router(ai.router)
app.include_router(export.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": "turso" if is_turso_configured() else "sqlite-local",
    }


# --- Frontend ------------------------------------------------------------- #
FRONTEND = settings.FRONTEND_DIR
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


def _page(name: str):
    path = FRONTEND / name
    if not path.exists():
        return JSONResponse({"detail": f"{name} not found"}, status_code=404)
    return FileResponse(path)


@app.get("/")
def landing():
    return _page("index.html")


@app.get("/login")
def login_page():
    return _page("login.html")


@app.get("/dashboard")
def dashboard_page():
    return _page("dashboard.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, reload=True)
