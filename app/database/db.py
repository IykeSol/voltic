"""SQLite access layer: schema creation and demo-account seeding.

In the input-driven model each account owns a `meter_profiles` row (household +
appliance inputs + balance). Usage is derived from that profile at request time,
so there is no bulk usage table to seed.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

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


class TursoHttpCursor:
    """DB-API compatible cursor backed by a Turso /v2/pipeline result."""

    def __init__(self, cols: list[str], rows: list[tuple], lastrowid: int | None):
        self._cols = cols
        self._rows = rows
        self._idx = 0
        self.lastrowid = lastrowid
        self.description = [(c,) for c in cols] if cols else None

    def fetchone(self) -> DictRow | None:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return DictRow(self._cols, row) if self._cols else row  # type: ignore[return-value]

    def fetchall(self) -> list[DictRow]:
        rem = self._rows[self._idx:]
        self._idx = len(self._rows)
        if not self._cols:
            return list(rem)  # type: ignore[return-value]
        return [DictRow(self._cols, r) for r in rem]

    def __iter__(self):
        return iter(self.fetchall())


def _encode_turso_arg(val: Any) -> dict[str, Any]:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    if isinstance(val, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(val)).decode("ascii")}
    return {"type": "text", "value": str(val)}


def _decode_turso_cell(cell: dict[str, Any]) -> Any:
    t = cell.get("type")
    if t == "null" or t is None:
        return None
    if t == "integer":
        return int(cell["value"])
    if t == "float":
        return float(cell["value"])
    if t == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return cell.get("value")


class TursoHttpConnection:
    """Zero-dependency Turso Hrana-over-HTTP (/v2/pipeline) connection.

    Works on Windows, Linux, Replit, and Hugging Face Spaces over standard
    HTTPS (port 443) without requiring native Rust/C libsql wheels.
    """

    def __init__(self, db_url: str, auth_token: str):
        url = db_url.strip().strip('"').strip("'").rstrip("/")
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        elif not url.startswith(("https://", "http://")):
            url = "https://" + url
        self._endpoint = f"{url}/v2/pipeline"
        self._token = auth_token.strip().strip('"').strip("'")

    def _send(self, requests_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        body = json.dumps({"requests": requests_payload}).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "voltic-turso-http/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Turso HTTP {e.code}: {err_body}") from e

        results = data.get("results", [])
        for r in results:
            if r.get("type") == "error":
                msg = r.get("error", {}).get("message", "Unknown Turso error")
                raise RuntimeError(f"Turso SQL error: {msg}")
        return results

    def execute(self, sql: str, params: tuple | list = ()) -> TursoHttpCursor:
        stmt: dict[str, Any] = {"sql": sql}
        if params:
            stmt["args"] = [_encode_turso_arg(p) for p in params]
        results = self._send([
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ])
        res = results[0]["response"]["result"]
        cols = [c["name"] for c in res.get("cols", [])]
        rows = [
            tuple(_decode_turso_cell(cell) for cell in row)
            for row in res.get("rows", [])
        ]
        raw_last = res.get("last_insert_rowid")
        lastrowid = int(raw_last) if raw_last is not None else None
        return TursoHttpCursor(cols, rows, lastrowid)

    def executescript(self, script: str) -> None:
        lines = [
            line for line in script.splitlines()
            if not line.strip().startswith("--")
        ]
        stmts = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
        if not stmts:
            return
        payload: list[dict[str, Any]] = [
            {"type": "execute", "stmt": {"sql": s}} for s in stmts
        ]
        payload.append({"type": "close"})
        self._send(payload)

    def commit(self) -> None:
        # Each /v2/pipeline request auto-commits unless inside an explicit BEGIN
        pass

    def close(self) -> None:
        pass


def is_turso_configured() -> bool:
    url = (os.getenv("TURSO_DATABASE_URL") or settings.TURSO_DATABASE_URL).strip()
    token = (os.getenv("TURSO_AUTH_TOKEN") or settings.TURSO_AUTH_TOKEN).strip()
    return bool(url and token)


@contextmanager
def get_conn():
    db_url = (os.getenv("TURSO_DATABASE_URL") or settings.TURSO_DATABASE_URL).strip()
    auth_token = (os.getenv("TURSO_AUTH_TOKEN") or settings.TURSO_AUTH_TOKEN).strip()

    conn: Any = None
    if db_url and auth_token:
        conn = TursoHttpConnection(db_url, auth_token)

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
    if is_turso_configured():
        url = (os.getenv("TURSO_DATABASE_URL") or settings.TURSO_DATABASE_URL).strip()
        print(f"[db] Using Turso cloud database: {url}")
    else:
        print(f"[db] Using local SQLite database ({settings.DB_PATH}) -- set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN for Turso")
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
