"""Read/write a user's meter profile, recharge log, and live balance depletion.

The balance behaves like a real prepaid meter: every time it is read we subtract
the predicted spend for the real time elapsed since it was last touched, then
persist the new value. Recharges add back to it.
"""

from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.database.db import get_conn


def get_profile(meter_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM meter_profiles WHERE meter_id = ?", (meter_id,)
        ).fetchone()
    return dict(row) if row else None


def has_profile(meter_id: str) -> bool:
    return get_profile(meter_id) is not None


def _daily_kwh(data: dict) -> float:
    from app.services.synthetic import estimate_daily_kwh  # local import avoids cycle

    return estimate_daily_kwh(data)


def upsert_profile(meter_id: str, data: dict) -> dict:
    now = datetime.utcnow().isoformat()
    daily_kwh = _daily_kwh(data)
    vals = (
        int(data["household_size"]), str(data["income_level"]), float(data["ac_hours"]),
        int(bool(data["has_fridge"])), float(data["tv_hours"]), float(data["fan_hours"]),
        float(data["washer_loads"]), float(data["balance"]), daily_kwh,
    )
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM meter_profiles WHERE meter_id = ?", (meter_id,)).fetchone():
            conn.execute(
                """UPDATE meter_profiles SET household_size=?, income_level=?, ac_hours=?,
                   has_fridge=?, tv_hours=?, fan_hours=?, washer_loads=?, balance=?, daily_kwh=?,
                   balance_ts=?, updated_at=? WHERE meter_id=?""",
                (*vals, now, now, meter_id),
            )
        else:
            conn.execute(
                """INSERT INTO meter_profiles
                   (meter_id, household_size, income_level, ac_hours, has_fridge,
                    tv_hours, fan_hours, washer_loads, balance, daily_kwh,
                    balance_ts, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (meter_id, *vals, now, now, now),
            )
    return get_profile(meter_id)


def settle_balance(meter_id: str) -> float | None:
    """Deplete the balance for real time elapsed since it was last settled."""
    prof = get_profile(meter_id)
    if not prof:
        return None

    now = datetime.utcnow()
    ts = prof.get("balance_ts")
    elapsed_seconds = 0.0
    if ts:
        try:
            elapsed_seconds = max(0.0, (now - datetime.fromisoformat(ts)).total_seconds())
        except ValueError:
            elapsed_seconds = 0.0
    elapsed_days = elapsed_seconds / 86400.0

    tariff = settings.TARIFF_BY_INCOME.get(str(prof["income_level"]), settings.DEFAULT_TARIFF)
    daily_cost = float(prof.get("daily_kwh") or 0) * tariff
    spent = elapsed_days * daily_cost
    new_balance = max(0.0, round(float(prof["balance"]) - spent, 4))

    # Persist when at least 5 seconds have elapsed (avoids 8x redundant writes during
    # parallel dashboard fetches while preserving sub-kobo precision).
    if (spent > 0 and elapsed_seconds >= 5.0) or not ts:
        with get_conn() as conn:
            conn.execute(
                "UPDATE meter_profiles SET balance=?, balance_ts=? WHERE meter_id=?",
                (new_balance, now.isoformat(), meter_id),
            )
    return round(new_balance, 2)


def add_recharge(meter_id: str, amount: float) -> float | None:
    # Settle first so the top-up is added to the correct, up-to-date balance.
    settle_balance(meter_id)
    prof = get_profile(meter_id)
    if not prof:
        return None

    new_balance = round(float(prof["balance"]) + float(amount), 2)
    now = datetime.utcnow()
    with get_conn() as conn:
        conn.execute(
            "UPDATE meter_profiles SET balance=?, balance_ts=? WHERE meter_id=?",
            (new_balance, now.isoformat(), meter_id),
        )
        conn.execute(
            """INSERT INTO recharge_history (meter_id, date, hour, amount, balance_after)
               VALUES (?,?,?,?,?)""",
            (meter_id, now.strftime("%Y-%m-%d"), now.hour, float(amount), new_balance),
        )
    return new_balance


def get_recharges(meter_id: str, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT date, hour, amount, balance_after FROM recharge_history
               WHERE meter_id = ? ORDER BY id DESC LIMIT ?""",
            (meter_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
