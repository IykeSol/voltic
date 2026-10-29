"""Render a user's profile into an hourly usage DataFrame.

The user tells us their household + how long each appliance runs per day. We
spread those hours across a realistic daily shape, convert to kWh, add light
noise for day-to-day variation, and draw the prepaid balance down to the value
they entered. Every downstream analytics/forecast service then works on this
DataFrame exactly as it did on the simulated dataset.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.config import settings
from app.services import profile_service

# kWh drawn per full hour of running (mirrors appliance_service / the dataset).
WATT = {"ac": 1.20, "fridge": 0.15, "tv": 0.10, "fan": 0.07, "washer": 0.50}

# Daily activity shapes (0..1 per hour) used to spread each appliance's hours.
_AC = [.6, .6, .5, .4, .2, .1, .05, .05, .05, .05, .1, .2, .5, .7, .8, .7, .5, .4, .5, .7, .8, .8, .7, .65]
_FAN = [.7, .7, .6, .5, .4, .3, .2, .2, .3, .4, .6, .8, .9, .9, .85, .7, .5, .4, .5, .7, .8, .85, .8, .75]
_TV = [.02, .01, .01, .01, .02, .05, .1, .15, .1, .08, .1, .2, .3, .25, .2, .25, .4, .6, .85, .95, .9, .7, .4, .1]
_WASH = [0, 0, 0, 0, 0, 0, 0, .2, .5, .8, .9, .8, .7, .6, .6, .7, .6, .4, .2, .05, 0, 0, 0, 0]
_LIGHT = [.2, .15, .1, .1, .15, .4, .6, .5, .3, .2, .2, .25, .3, .3, .3, .35, .45, .7, .95, 1, .95, .8, .55, .3]

_MONTH_TEMP = {1: 33, 2: 35, 3: 35, 4: 33, 5: 31, 6: 29, 7: 28, 8: 28, 9: 29, 10: 30, 11: 32, 12: 32}
_MONTH_HUM = {1: 35, 2: 40, 3: 50, 4: 65, 5: 75, 6: 82, 7: 85, 8: 85, 9: 83, 10: 78, 11: 60, 12: 45}


def _distribute(shape: list[float], daily_hours: float) -> np.ndarray:
    s = np.array(shape, dtype=float)
    if s.sum() <= 0 or daily_hours <= 0:
        return np.zeros(24)
    return np.clip(s / s.sum() * daily_hours, 0, 1)


def _seed(meter_id: str) -> int:
    # Stable across processes (str hashing is randomised, so use md5).
    return int(hashlib.md5(meter_id.encode()).hexdigest()[:8], 16)


def estimate_daily_kwh(prof: dict) -> float:
    """Quick estimate of a profile's daily kWh (used for balance depletion).

    Pure function of the profile inputs - no DB or simulation - so it can be
    called cheaply whenever the balance needs settling.
    """
    hh = float(prof["household_size"])
    daily = (
        float(prof["ac_hours"]) * WATT["ac"]
        + float(prof["tv_hours"]) * WATT["tv"]
        + float(prof["fan_hours"]) * WATT["fan"]
        + (float(prof["washer_loads"] or 0) / 7.0) * WATT["washer"]
    )
    if prof["has_fridge"]:
        daily += 0.45 * 24 * WATT["fridge"]
    daily += sum(_LIGHT) * (0.5 + 0.08 * hh) * 0.06   # lighting
    daily += 0.03 * (0.6 + 0.1 * hh) * 24             # baseline (router, charging)
    return round(daily, 3)


def build_user_df(meter_id: str, days: int = 30) -> pd.DataFrame:
    prof = profile_service.get_profile(meter_id)
    if not prof:
        return pd.DataFrame()

    rng = np.random.default_rng(_seed(meter_id))
    income = str(prof["income_level"])
    tariff = settings.TARIFF_BY_INCOME.get(income, settings.DEFAULT_TARIFF)
    hh = int(prof["household_size"])

    ac = _distribute(_AC, float(prof["ac_hours"]))
    fan = _distribute(_FAN, float(prof["fan_hours"]))
    tv = _distribute(_TV, float(prof["tv_hours"]))
    wash = _distribute(_WASH, float(prof["washer_loads"] or 0) / 7.0)
    fridge_base = 0.45 if prof["has_fridge"] else 0.0
    light = np.array(_LIGHT)

    end = datetime.now().date()
    rows: list[dict] = []
    for d in range(days - 1, -1, -1):
        date = end - timedelta(days=d)
        is_weekend = date.weekday() >= 5
        day_type = "weekend" if is_weekend else "weekday"
        boost = 1.12 if is_weekend else 1.0
        day_temp = _MONTH_TEMP[date.month] + rng.normal(0, 1.5)
        day_hum = float(np.clip(_MONTH_HUM[date.month] + rng.normal(0, 4), 15, 99))

        for h in range(24):
            ac_h = float(np.clip(ac[h] * boost * rng.normal(1, 0.12), 0, 1))
            fan_h = float(np.clip(fan[h] * boost * rng.normal(1, 0.12), 0, 1))
            tv_h = float(np.clip(tv[h] * boost * rng.normal(1, 0.12), 0, 1))
            wash_h = float(np.clip(wash[h] * rng.normal(1, 0.20), 0, 1))
            fridge_h = float(np.clip(fridge_base * rng.normal(1, 0.08), 0, 1)) if fridge_base else 0.0

            lighting = light[h] * (0.5 + 0.08 * hh) * 0.06
            baseline = 0.03 * (0.6 + 0.1 * hh)
            units = (ac_h * WATT["ac"] + fridge_h * WATT["fridge"] + tv_h * WATT["tv"]
                     + fan_h * WATT["fan"] + wash_h * WATT["washer"] + lighting + baseline)
            units = max(0.0, units * rng.normal(1, 0.06))
            temp = round(day_temp + np.sin((h - 15) / 24 * 2 * np.pi) * 3 + rng.normal(0, 0.6), 1)

            rows.append({
                "meter_id": meter_id, "date": date.strftime("%Y-%m-%d"), "hour": h,
                "temperature": temp, "humidity": round(day_hum, 1), "day_type": day_type,
                "power_outage": 0, "household_size": hh, "income_level": income,
                "ac_usage_hours": round(ac_h, 3), "fridge_usage": round(fridge_h, 3),
                "tv_usage_hours": round(tv_h, 3), "fan_usage_hours": round(fan_h, 3),
                "washing_machine_usage": round(wash_h, 3),
                "units_consumed_kwh": round(units, 4),
                "recharge_amount": 0.0, "remaining_balance": 0.0, "anomaly": 0,
            })

    # Inject a few realistic prepaid-meter events over the recent window (overnight
    # appliance left running, compressor surge, or peak load spike) so anomaly
    # detection works naturally on any active meter profile.
    event_specs = [
        # (days_ago, hour, kind)
        (2, 2, "night"),
        (5, 19, "spike"),
        (9, 3, "night"),
        (13, 14, "fault"),
    ]
    total_rows = len(rows)
    for d_ago, target_h, kind in event_specs:
        idx = (days - 1 - d_ago) * 24 + target_h
        if 0 <= idx < total_rows:
            r = rows[idx]
            if kind == "night":
                r["ac_usage_hours"] = round(min(1.0, r["ac_usage_hours"] + 0.35), 3)
                r["units_consumed_kwh"] = round(r["units_consumed_kwh"] + rng.uniform(3.2, 4.2), 4)
            elif kind == "spike":
                r["ac_usage_hours"] = 1.0
                r["washing_machine_usage"] = 0.95
                r["units_consumed_kwh"] = round(r["units_consumed_kwh"] + rng.uniform(2.8, 3.8), 4)
            elif kind == "fault":
                r["fridge_usage"] = 1.0
                r["units_consumed_kwh"] = round(r["units_consumed_kwh"] + rng.uniform(2.5, 3.4), 4)
            r["anomaly"] = 1

    df = pd.DataFrame(rows)

    # Draw the balance down so the latest reading equals the stored balance.
    cost = df["units_consumed_kwh"] * tariff
    cost_after = cost[::-1].cumsum()[::-1].shift(-1).fillna(0.0)
    df["remaining_balance"] = (float(prof["balance"]) + cost_after).round(2)

    df["timestamp"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit="h")
    df["day_of_week"] = pd.to_datetime(df["date"]).dt.dayofweek
    return df
