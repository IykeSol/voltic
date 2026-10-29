"""Central application configuration, loaded once at import time."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


class Settings:
    PROJECT_NAME = "Prepaid Meter Usage Pattern Analyzer"
    VERSION = "1.0.0"

    # Paths
    ROOT_DIR = ROOT_DIR
    DATA_PATH = ROOT_DIR / "dataset" / "prepaid_meter_dataset.csv"
    MODEL_DIR = ROOT_DIR / "trained_models"
    DB_PATH = ROOT_DIR / "app" / "database" / "meter.db"
    FRONTEND_DIR = ROOT_DIR / "frontend"

    # Turso / LibSQL (Persistent Cloud SQLite)
    TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
    TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

    # Auth / JWT
    JWT_SECRET = os.getenv("JWT_SECRET", "prepaid-meter-dev-secret-change-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

    # Billing assumptions (Naira per kWh) used for balance / budget maths.
    DEFAULT_TARIFF = float(os.getenv("DEFAULT_TARIFF", "68.0"))
    TARIFF_BY_INCOME = {"low": 60.0, "middle": 68.0, "high": 75.0}


settings = Settings()
