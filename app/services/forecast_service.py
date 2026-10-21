"""Usage forecasting built on the trained RandomForest model.

Future days are projected by feeding the model each meter's own typical
behavioural profile (by day-type and hour), then bias-correcting the output so
it matches the household's recent reality.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import settings
from app.services.data_access import load_meter_df, tariff_for

_PROFILE_COLS = [
    "temperature", "humidity", "power_outage", "ac_usage_hours",
    "fridge_usage", "tv_usage_hours", "fan_usage_hours", "washing_machine_usage",
]


@lru_cache(maxsize=1)
def _load_model():
    import joblib

    path = settings.MODEL_DIR / "usage_model.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


def _bias_correction(model, df: pd.DataFrame) -> float:
    """Ratio that aligns model output with the meter's recent actual usage."""
    recent = df.tail(14 * 24)
    if recent.empty:
        return 1.0
    feats = model["features"]
    pred = model["pipeline"].predict(recent[feats])
    pred_daily = pred.sum() / max(recent["date"].nunique(), 1)
    actual_daily = recent.groupby("date")["units_consumed_kwh"].sum().mean()
    if pred_daily <= 1e-6:
        return 1.0
    return float(np.clip(actual_daily / pred_daily, 0.6, 1.6))


def _hourly_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Mean feature values per (day_type, hour) for this meter."""
    prof = df.groupby(["day_type", "hour"])[_PROFILE_COLS].mean().reset_index()
    return prof.fillna(df[_PROFILE_COLS].mean())


def _spike_probability(df: pd.DataFrame) -> float:
    daily = df.groupby("date")["units_consumed_kwh"].sum()
    if len(daily) < 5:
        return 0.1
    last14 = daily.tail(14)
    cv = last14.std() / max(last14.mean(), 1e-6)
    recent_jump = last14.tail(3).max() / max(last14.mean(), 1e-6) - 1
    prob = 0.12 + 0.7 * (cv - 0.25) + 0.45 * max(recent_jump, 0)
    return round(float(np.clip(prob, 0.02, 0.95)), 2)


def forecast(meter_id: str, horizon: int = 7) -> dict:
    df = load_meter_df(meter_id)
    if df.empty:
        return {"available": False}

    tariff = tariff_for(df)
    balance = float(df["remaining_balance"].iloc[-1])
    last_date = pd.to_datetime(df["date"].iloc[-1])
    household = int(df["household_size"].iloc[-1])
    income = str(df["income_level"].iloc[-1])

    model = _load_model()
    daily_hist = df.groupby("date")["units_consumed_kwh"].sum()

    next_days: list[dict] = []
    if model is None:
        # Fallback: weekday/weekend historical averages if the model is absent.
        wd = df[df["day_type"] == "weekday"].groupby("date")["units_consumed_kwh"].sum().mean()
        we = df[df["day_type"] == "weekend"].groupby("date")["units_consumed_kwh"].sum().mean()
        for i in range(1, horizon + 1):
            d = last_date + timedelta(days=i)
            is_we = d.weekday() >= 5
            kwh = float(we if is_we else wd)
            next_days.append(_day_entry(d, kwh, tariff))
    else:
        profile = _hourly_profile(df)
        correction = _bias_correction(model, df)
        feats = model["features"]
        for i in range(1, horizon + 1):
            d = last_date + timedelta(days=i)
            day_type = "weekend" if d.weekday() >= 5 else "weekday"
            block = profile[profile["day_type"] == day_type].copy()
            if block.empty:
                block = profile.copy()
            frame = pd.DataFrame({
                "hour": block["hour"].values,
                "temperature": block["temperature"].values,
                "humidity": block["humidity"].values,
                "household_size": household,
                "power_outage": block["power_outage"].values,
                "day_of_week": d.weekday(),
                "ac_usage_hours": block["ac_usage_hours"].values,
                "fridge_usage": block["fridge_usage"].values,
                "tv_usage_hours": block["tv_usage_hours"].values,
                "fan_usage_hours": block["fan_usage_hours"].values,
                "washing_machine_usage": block["washing_machine_usage"].values,
                "day_type": day_type,
                "income_level": income,
            })
            kwh = float(model["pipeline"].predict(frame[feats]).sum() * correction)
            next_days.append(_day_entry(d, kwh, tariff))

    # Recharge exhaustion: walk the balance down using the forecast.
    avg_future_cost = np.mean([d["predicted_cost"] for d in next_days]) or 1.0
    remaining, day_counter, exhaustion_date = balance, 0, None
    while remaining > 0 and day_counter < 120:
        cost = next_days[day_counter]["predicted_cost"] if day_counter < len(next_days) else avg_future_cost
        remaining -= cost
        day_counter += 1
    exhaustion_date = (last_date + timedelta(days=day_counter)).strftime("%Y-%m-%d")

    return {
        "available": True,
        "tomorrow_kwh": next_days[0]["predicted_kwh"],
        "next_days": next_days,
        "next7_total_kwh": round(sum(d["predicted_kwh"] for d in next_days), 1),
        "recharge_exhaustion_date": exhaustion_date,
        "days_until_exhaustion": day_counter,
        "spike_probability": _spike_probability(df),
        "history_tail": [
            {"date": d, "kwh": round(float(v), 2)} for d, v in daily_hist.tail(14).items()
        ],
    }


def _day_entry(d: pd.Timestamp, kwh: float, tariff: float) -> dict:
    kwh = max(0.0, round(kwh, 2))
    return {
        "date": d.strftime("%Y-%m-%d"),
        "day_type": "weekend" if d.weekday() >= 5 else "weekday",
        "predicted_kwh": kwh,
        "predicted_cost": round(kwh * tariff, 0),
    }
