"""Descriptive analytics: dashboard summary, history, peak hours, heatmap."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.services import profile_service
from app.services.data_access import load_meter_df, tariff_for

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _daily_totals(df: pd.DataFrame) -> pd.Series:
    return df.groupby("date")["units_consumed_kwh"].sum()


def get_summary(meter_id: str) -> dict:
    df = load_meter_df(meter_id)
    if df.empty:
        return {"has_data": False}

    tariff = tariff_for(df)
    daily = _daily_totals(df)
    last_date = pd.to_datetime(df["date"].iloc[-1])

    last30 = daily.tail(30)
    avg_daily = float(last30.mean())
    total_month = float(last30.sum())
    balance = float(df["remaining_balance"].iloc[-1])
    avg_daily_cost = max(avg_daily * tariff, 1e-6)
    days_left = balance / avg_daily_cost
    exhaustion = (last_date + timedelta(days=days_left)).strftime("%Y-%m-%d")

    by_hour = df.groupby("hour")["units_consumed_kwh"].mean()
    peak_hour = int(by_hour.idxmax())

    # Recharge cadence over the visible history.
    recharges = df[df["recharge_amount"] > 0]
    span_days = max((last_date - pd.to_datetime(df["date"].iloc[0])).days, 1)
    recharge_freq_days = round(span_days / len(recharges), 1) if len(recharges) else None

    weekday = df[df["day_type"] == "weekday"].groupby("date")["units_consumed_kwh"].sum().mean()
    weekend = df[df["day_type"] == "weekend"].groupby("date")["units_consumed_kwh"].sum().mean()

    return {
        "has_data": True,
        "meter_id": meter_id,
        "household_size": int(df["household_size"].iloc[-1]),
        "income_level": str(df["income_level"].iloc[-1]),
        "tariff": round(tariff, 2),
        "total_month_kwh": round(total_month, 1),
        "avg_daily_kwh": round(avg_daily, 2),
        "remaining_balance": round(balance, 2),
        "avg_daily_cost": round(avg_daily_cost, 2),
        "days_to_exhaustion": round(days_left, 1),
        "predicted_exhaustion_date": exhaustion,
        "peak_hour": peak_hour,
        "peak_hour_label": f"{peak_hour:02d}:00",
        "recharge_frequency_days": recharge_freq_days,
        "weekday_avg_kwh": round(float(weekday), 2) if not np.isnan(weekday) else None,
        "weekend_avg_kwh": round(float(weekend), 2) if not np.isnan(weekend) else None,
        "days_of_history": int(daily.shape[0]),
        "last_reading_date": df["date"].iloc[-1],
    }


def get_history(meter_id: str, days: int = 30) -> dict:
    df = load_meter_df(meter_id, days=days)
    if df.empty:
        return {"daily": [], "recharges": []}

    tariff = tariff_for(df)
    daily = _daily_totals(df).reset_index()
    daily.columns = ["date", "kwh"]
    daily["cost"] = (daily["kwh"] * tariff).round(0)
    daily["kwh"] = daily["kwh"].round(2)

    # Recharges are the user's own logged top-ups, not part of the usage series.
    recharges = [
        {"date": r["date"], "hour": int(r["hour"]),
         "amount": float(r["amount"]), "balance_after": round(float(r["balance_after"]), 2)}
        for r in profile_service.get_recharges(meter_id)
    ]
    return {"daily": daily.to_dict(orient="records"), "recharges": recharges}


def get_peak_hours(meter_id: str) -> dict:
    df = load_meter_df(meter_id)
    if df.empty:
        return {"hours": list(range(24)), "values": [0] * 24}
    by_hour = df.groupby("hour")["units_consumed_kwh"].mean().reindex(range(24), fill_value=0)
    return {"hours": list(range(24)), "values": [round(float(v), 3) for v in by_hour.values]}


def get_heatmap(meter_id: str) -> dict:
    """Average kWh per (day-of-week, hour) - the activity heatmap grid."""
    df = load_meter_df(meter_id)
    if df.empty:
        return {"days": WEEKDAY_LABELS, "hours": list(range(24)), "matrix": []}

    pivot = (
        df.groupby(["day_of_week", "hour"])["units_consumed_kwh"]
        .mean()
        .unstack(fill_value=0)
        .reindex(index=range(7), columns=range(24), fill_value=0)
    )
    matrix = [[round(float(v), 3) for v in row] for row in pivot.values]
    return {"days": WEEKDAY_LABELS, "hours": list(range(24)), "matrix": matrix}


def get_trends(meter_id: str, days: int = 14) -> dict:
    """Recent daily series plus weekday/weekend split for the trends panel."""
    df = load_meter_df(meter_id, days=days)
    if df.empty:
        return {"daily": [], "weekday_avg": 0, "weekend_avg": 0}
    daily = _daily_totals(df)
    wd = df[df["day_type"] == "weekday"].groupby("date")["units_consumed_kwh"].sum().mean()
    we = df[df["day_type"] == "weekend"].groupby("date")["units_consumed_kwh"].sum().mean()
    return {
        "daily": [{"date": d, "kwh": round(float(v), 2)} for d, v in daily.items()],
        "weekday_avg": round(float(wd), 2) if not np.isnan(wd) else 0,
        "weekend_avg": round(float(we), 2) if not np.isnan(we) else 0,
    }
