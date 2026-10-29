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


class DictRow:
    """Provides sqlite3.Row-compatible dictionary and index access."""
    __slots__ = ("_cols", "_vals", "_d")

    def __init__(self, cols: list[str], vals: tuple):
        self._cols = cols
        self._vals = vals
        self._d = dict(zip(cols, vals))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()

    def items(self):
        return self._d.items()

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def __repr__(self):
        return repr(self._d)


class TursoCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)

    @property
    def description(self):
        return getattr(self._cursor, "description", None)

    def _wrap(self, row):
        if row is None:
            return None
        if self._cursor.description:
            cols = [col[0] for col in self._cursor.description]
            return DictRow(cols, row)
        return row

    def fetchone(self):
        return self._wrap(self._cursor.fetchone())

    def fetchall(self):
        desc = self._cursor.description
        if not desc:
            return self._cursor.fetchall()
        cols = [col[0] for col in desc]
        return [DictRow(cols, r) for r in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class TursoConnWrapper:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: tuple | list = ()):
        cur = self._conn.cursor()
        if params:
            cur.execute(sql, tuple(params))
        else:
            cur.execute(sql)
        return TursoCursorWrapper(cur)

    def executescript(self, script: str):
        # Strip comments and split by semicolon
        lines = []
        for line in script.splitlines():
            stripped = line.strip()
            if not stripped.startswith("--"):
                lines.append(line)
        cleaned = "\n".join(lines)
        for stmt in cleaned.split(";"):
            s = stmt.strip()
            if s:
                self.execute(s)

    def commit(self):
        self._conn.commit()

    def close(self):
        if hasattr(self._conn, "close"):
            self._conn.close()


@contextmanager
def get_conn():
    conn = None
    if settings.TURSO_DATABASE_URL and settings.TURSO_AUTH_TOKEN:
        try:
            import libsql  # type: ignore
            raw_conn = libsql.connect(
                database=settings.TURSO_DATABASE_URL,
                auth_token=settings.TURSO_AUTH_TOKEN,
            )
            conn = TursoConnWrapper(raw_conn)
        except Exception as e:
            print(f"[db] Turso connection error, falling back to local SQLite: {e}")

    if conn is None:
        # Fallback: standard local SQLite
        settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        raw_sqlite = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        raw_sqlite.row_factory = sqlite3.Row
        conn = raw_sqlite

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


def assign_meter_for_new_user(conn=None) -> str:
    """Mint a fresh meter label for a new signup (no usage history attached)."""
    if conn is not None:
        n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    else:
        with get_conn() as c:
            n = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    return f"MTR-U{n + 1:04d}"
