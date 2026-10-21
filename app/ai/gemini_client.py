"""Thin wrapper around the Gemini API with a safe offline fallback."""

from __future__ import annotations

from app.config import settings

_client = None
_init_done = False


def _get_client():
    global _client, _init_done
    if _init_done:
        return _client
    _init_done = True
    key = settings.GEMINI_API_KEY
    if not key or key.lower().startswith("your_"):
        _client = None
        return None
    try:
        from google import genai

        _client = genai.Client(api_key=key)
    except Exception as exc:  # noqa: BLE001 - never let AI setup crash the app
        print(f"[gemini] client unavailable: {exc}")
        _client = None
    return _client


def is_available() -> bool:
    return _get_client() is not None


def generate(prompt: str, temperature: float = 0.6) -> str | None:
    """Return model text, or None if Gemini is unavailable / errors out."""
    client = _get_client()
    if client is None:
        return None
    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return (resp.text or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] generation failed: {exc}")
        return None
