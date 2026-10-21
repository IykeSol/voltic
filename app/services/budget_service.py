"""Budget / recharge recommendation engine."""

from __future__ import annotations

import math

from app.services.data_access import load_meter_df, tariff_for


def _round_to(amount: float, step: int = 500) -> int:
    return int(max(step, math.ceil(amount / step) * step))


def recommend(meter_id: str, cover_days: int = 14) -> dict:
    df = load_meter_df(meter_id, days=30)
    if df.empty:
        return {"available": False}

    tariff = tariff_for(df)
    daily = df.groupby("date")["units_consumed_kwh"].sum()
    avg_daily_kwh = float(daily.mean())
    avg_daily_cost = avg_daily_kwh * tariff
    balance = float(df["remaining_balance"].iloc[-1])

    target_cost = avg_daily_cost * cover_days
    # Top up to the target buffer, accounting for what is already loaded.
    suggested = _round_to(max(target_cost - balance, avg_daily_cost * 3))

    return {
        "available": True,
        "recommended_amount": suggested,
        "covers_days": round(suggested / max(avg_daily_cost, 1e-6), 1),
        "avg_daily_cost": round(avg_daily_cost, 2),
        "avg_daily_kwh": round(avg_daily_kwh, 2),
        "current_balance": round(balance, 2),
        "tariff": round(tariff, 2),
        "cover_target_days": cover_days,
    }
