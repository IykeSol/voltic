"""SQLite access layer: schema creation and demo-account seeding.

In the input-driven model each account owns a `meter_profiles` row (household +
appliance inputs + balance). Usage is derived from that profile at request time,
so there is no bulk usage table to seed.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from app.config import settings

SCHEMA = """
-- The old simulation-era usage table is no longer used; drop it if present.
DROP TABLE IF EXISTS meter_usage;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    meter_id      TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS meter_profiles (
    meter_id       TEXT PRIMARY KEY,
    household_size INTEGER,
    income_level   TEXT,
    ac_hours       REAL,
    has_fridge     INTEGER,
    tv_hours       REAL,
    fan_hours      REAL,
    washer_loads   REAL,
    balance        REAL,
    daily_kwh      REAL DEFAULT 0,
    balance_ts     TEXT,
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS recharge_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_id      TEXT,
    date          TEXT,
    hour          INTEGER,
    amount        REAL,
    balance_after REAL
);

CREATE TABLE IF NOT EXISTS predictions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    created_at TEXT,
    payload    TEXT
);

CREATE INDEX IF NOT EXISTS idx_recharge_meter ON recharge_history(meter_id);
"""

DEMO_METER = "MTR-DEMO"
DEMO_PROFILE = {
    "household_size": 4, "income_level": "middle", "ac_hours": 5.0,
    "has_fridge": 1, "tv_hours": 6.0, "fan_hours": 10.0,
    "washer_loads": 3.0, "balance": 8000.0,
}


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn) -> None:
    """Add columns / backfill values introduced after a DB was first created."""
    from app.services.synthetic import estimate_daily_kwh

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(meter_profiles)")}
    if "daily_kwh" not in cols:
        conn.execute("ALTER TABLE meter_profiles ADD COLUMN daily_kwh REAL DEFAULT 0")
    if "balance_ts" not in cols:
        conn.execute("ALTER TABLE meter_profiles ADD COLUMN balance_ts TEXT")

    # Backfill depletion rate + anchor timestamp for any pre-existing profiles.
    now = datetime.utcnow().isoformat()
    pending = conn.execute(
        "SELECT * FROM meter_profiles WHERE daily_kwh IS NULL OR daily_kwh <= 0 OR balance_ts IS NULL"
    ).fetchall()
    for r in pending:
        est = estimate_daily_kwh(dict(r))
        conn.execute(
            "UPDATE meter_profiles SET daily_kwh=?, balance_ts=COALESCE(balance_ts, ?) WHERE meter_id=?",
            (est, now, r["meter_id"]),
        )


def seed_if_empty() -> None:
    """Ensure a ready-to-use demo account (pre-filled profile) exists."""
    from app.utils.security import hash_password

    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        demo = conn.execute(
            "SELECT id, meter_id FROM users WHERE email = ?", ("demo@meter.ng",)
        ).fetchone()
        if demo is None:
            conn.execute(
                """INSERT INTO users (full_name, email, password_hash, meter_id, created_at)
                   VALUES (?,?,?,?,?)""",
                ("Demo User", "demo@meter.ng", hash_password("demo1234"), DEMO_METER, now),
            )
            print("[seed] Demo account ready -> demo@meter.ng / demo1234")

        # Make sure the demo meter has a populated profile so it isn't blank.
        has_profile = conn.execute(
            "SELECT 1 FROM meter_profiles WHERE meter_id = ?", (DEMO_METER,)
        ).fetchone()
        if has_profile is None:
            from app.services.synthetic import estimate_daily_kwh

            p = DEMO_PROFILE
            conn.execute(
                """INSERT INTO meter_profiles
                   (meter_id, household_size, income_level, ac_hours, has_fridge,
                    tv_hours, fan_hours, washer_loads, balance, daily_kwh,
                    balance_ts, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (DEMO_METER, p["household_size"], p["income_level"], p["ac_hours"],
                 p["has_fridge"], p["tv_hours"], p["fan_hours"], p["washer_loads"],
                 p["balance"], estimate_daily_kwh(p), now, now, now),
            )


def assign_meter_for_new_user() -> str:
    """Mint a fresh meter label for a new signup (no usage history attached)."""
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    return f"MTR-U{n + 1:04d}"
