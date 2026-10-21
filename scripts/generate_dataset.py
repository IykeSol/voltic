"""
Realistic prepaid electricity meter dataset generator.

Simulates hourly electricity behaviour for a set of Nigerian households on
prepaid meters. The output is intentionally imperfect: it carries measurement
noise, occasional missing readings, random grid outages and injected anomalies
so that a model trained on it lands in a believable 0.70-0.80 R2 band instead
of an unrealistic 0.95+.

Run:
    python scripts/generate_dataset.py
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "dataset" / "prepaid_meter_dataset.csv"

SEED = 42
N_METERS = 30                 # households
N_DAYS = 70                   # days of hourly history per household
END_DATE = datetime(2026, 6, 10)  # most recent day in the dataset
TARGET_ROWS = N_METERS * N_DAYS * 24  # 30 * 70 * 24 = 50,400 rows

# Appliance instantaneous draw, in kWh consumed across one full hour of running.
APPLIANCE_KWH = {
    "ac": 1.20,
    "fridge": 0.15,      # per running (duty-cycle) hour
    "tv": 0.10,
    "fan": 0.07,
    "washing": 0.50,
}

# Per-income appliance ownership probability and behaviour envelopes.
INCOME_PROFILE = {
    "low": {
        "own_fridge": 0.60, "own_ac": 0.00, "own_tv": 0.90,
        "own_washing": 0.05, "household": (3, 8),
        "outage_rate": 0.30, "tariff": 60.0,
        "recharge_choices": [500, 1000, 1000, 2000],
    },
    "middle": {
        "own_fridge": 0.95, "own_ac": 0.25, "own_tv": 1.00,
        "own_washing": 0.40, "household": (2, 6),
        "outage_rate": 0.20, "tariff": 68.0,
        "recharge_choices": [1000, 2000, 2000, 5000],
    },
    "high": {
        "own_fridge": 1.00, "own_ac": 0.90, "own_tv": 1.00,
        "own_washing": 0.85, "household": (2, 5),
        "outage_rate": 0.12, "tariff": 75.0,
        "recharge_choices": [5000, 5000, 10000, 20000],
    },
}

# Rough Nigerian monthly climate (avg daytime temp C, relative humidity %).
MONTH_CLIMATE = {
    1: (33, 35), 2: (35, 40), 3: (35, 50), 4: (33, 65),
    5: (31, 75), 6: (29, 82), 7: (28, 85), 8: (28, 85),
    9: (29, 83), 10: (30, 78), 11: (32, 60), 12: (32, 45),
}


def hour_profile(hour: int) -> dict:
    """Return baseline activity weights (0..1) for a given hour of day."""
    # Lighting / general baseline: low overnight, peaks in the evening.
    lighting = 0.15
    if 5 <= hour <= 7:
        lighting = 0.45
    elif 18 <= hour <= 23:
        lighting = 0.85
    elif 0 <= hour <= 4:
        lighting = 0.20

    # Fan demand: midday heat + overnight sleeping comfort.
    fan = 0.2
    if 12 <= hour <= 16:
        fan = 0.85
    elif 22 <= hour or hour <= 5:
        fan = 0.75

    # AC: hot afternoons and through the night for those who own one.
    ac = 0.0
    if 13 <= hour <= 16:
        ac = 0.7
    elif 21 <= hour or hour <= 4:
        ac = 0.85

    # TV: mostly evening, some midday.
    tv = 0.05
    if 18 <= hour <= 23:
        tv = 0.8
    elif 12 <= hour <= 15:
        tv = 0.35

    return {"lighting": lighting, "fan": fan, "ac": ac, "tv": tv}


def build_meter(meter_idx: int, rng: random.Random) -> dict:
    """Create static attributes for one household/meter."""
    income = rng.choices(
        ["low", "middle", "high"], weights=[0.45, 0.40, 0.15]
    )[0]
    prof = INCOME_PROFILE[income]
    lo, hi = prof["household"]
    return {
        "meter_id": f"MTR-{4000 + meter_idx:04d}",
        "user_id": f"U{meter_idx + 1:03d}",
        "income_level": income,
        "household_size": rng.randint(lo, hi),
        "has_fridge": rng.random() < prof["own_fridge"],
        "has_ac": rng.random() < prof["own_ac"],
        "has_tv": rng.random() < prof["own_tv"],
        "has_washing": rng.random() < prof["own_washing"],
        "tariff": prof["tariff"],
        "outage_rate": prof["outage_rate"] * rng.uniform(0.7, 1.3),
        "recharge_choices": prof["recharge_choices"],
        "balance": rng.uniform(800, 6000),
    }


def generate() -> pd.DataFrame:
    rng = random.Random(SEED)
    np.random.seed(SEED)

    meters = [build_meter(i, rng) for i in range(N_METERS)]
    rows: list[dict] = []

    for meter in meters:
        balance = meter["balance"]
        tariff = meter["tariff"]
        size_factor = 0.6 + 0.12 * meter["household_size"]

        for day_offset in range(N_DAYS):
            date = END_DATE - timedelta(days=(N_DAYS - 1 - day_offset))
            is_weekend = date.weekday() >= 5
            day_type = "weekend" if is_weekend else "weekday"

            base_temp, base_hum = MONTH_CLIMATE[date.month]
            day_temp = base_temp + rng.uniform(-2.5, 2.5)
            day_hum = min(98, max(20, base_hum + rng.uniform(-8, 8)))
            heat = max(0.0, (day_temp - 29) / 6.0)  # 0..~1 "how hot" driver

            # Each day draws its own grid reliability around the income base.
            day_outage_rate = min(0.6, max(0.0, meter["outage_rate"] + rng.uniform(-0.08, 0.08)))

            for hour in range(24):
                prof = hour_profile(hour)
                outage = 1 if rng.random() < day_outage_rate else 0

                # Hourly weather wobble around the daily value.
                temperature = round(day_temp + math.sin((hour - 15) / 24 * 2 * math.pi) * 3
                                    + rng.uniform(-1, 1), 1)
                humidity = round(min(99, max(15, day_hum - (temperature - day_temp) * 1.2
                                             + rng.uniform(-3, 3))), 1)

                if outage:
                    # No grid power -> nothing draws from the prepaid meter.
                    ac_h = fridge_h = tv_h = fan_h = wash_h = 0.0
                    units = 0.0
                else:
                    weekend_boost = 1.15 if is_weekend else 1.0

                    fan_h = (prof["fan"] * (0.5 + heat) * weekend_boost
                             * rng.uniform(0.7, 1.1)) if True else 0.0
                    fan_h = min(1.0, max(0.0, fan_h))

                    ac_h = 0.0
                    if meter["has_ac"]:
                        ac_h = min(1.0, max(0.0, prof["ac"] * (0.3 + heat * 1.3)
                                            * rng.uniform(0.6, 1.1)))

                    tv_h = 0.0
                    if meter["has_tv"]:
                        tv_h = min(1.0, max(0.0, prof["tv"] * weekend_boost * rng.uniform(0.7, 1.1)))

                    fridge_h = 0.0
                    if meter["has_fridge"]:
                        # Compressor duty cycle, a little higher when hot.
                        fridge_h = min(1.0, max(0.0, (0.40 + 0.18 * heat) * rng.uniform(0.85, 1.15)))

                    wash_h = 0.0
                    if meter["has_washing"] and 8 <= hour <= 18:
                        wash_prob = 0.10 if is_weekend else 0.04
                        if rng.random() < wash_prob:
                            wash_h = rng.uniform(0.4, 1.0)

                    lighting = prof["lighting"] * size_factor * rng.uniform(0.8, 1.15)
                    baseline = 0.04 * size_factor  # phone charging, router, etc.

                    units = (
                        ac_h * APPLIANCE_KWH["ac"]
                        + fridge_h * APPLIANCE_KWH["fridge"]
                        + tv_h * APPLIANCE_KWH["tv"]
                        + fan_h * APPLIANCE_KWH["fan"]
                        + wash_h * APPLIANCE_KWH["washing"]
                        + lighting * 0.06
                        + baseline
                        + temperature * 0.002  # weak weather coupling
                    )

                    # Imperfect meter: multiplicative + additive measurement noise.
                    # The noise level is deliberately high so a model trained on
                    # this data scores in a realistic 0.70-0.80 R2 band.
                    units *= 1 + np.random.normal(0, 0.34)
                    units += np.random.normal(0, 0.09)
                    units = max(0.0, units)

                anomaly = 0
                # Inject rare, clearly abnormal events into live (non-outage) hours.
                if not outage and rng.random() < 0.004:
                    kind = rng.random()
                    if kind < 0.4 and 0 <= hour <= 4:
                        units += rng.uniform(3.5, 6.0)       # night tampering / bypass
                    elif kind < 0.7:
                        units += rng.uniform(2.5, 5.0)       # appliance malfunction
                        fridge_h = 1.0
                    else:
                        units *= rng.uniform(3.0, 5.0)       # raw consumption spike
                    anomaly = 1

                # --- Billing: draw down the prepaid balance, recharge when low ---
                balance -= units * tariff
                recharge_amount = 0.0
                if balance < rng.uniform(150, 400):
                    recharge_amount = float(rng.choice(meter["recharge_choices"]))
                    balance += recharge_amount

                rows.append({
                    "user_id": meter["user_id"],
                    "meter_id": meter["meter_id"],
                    "date": date.strftime("%Y-%m-%d"),
                    "hour": hour,
                    "temperature": temperature,
                    "humidity": humidity,
                    "day_type": day_type,
                    "power_outage": outage,
                    "household_size": meter["household_size"],
                    "income_level": meter["income_level"],
                    "ac_usage_hours": round(ac_h, 3),
                    "fridge_usage": round(fridge_h, 3),
                    "tv_usage_hours": round(tv_h, 3),
                    "fan_usage_hours": round(fan_h, 3),
                    "washing_machine_usage": round(wash_h, 3),
                    "units_consumed_kwh": round(units, 4),
                    "recharge_amount": recharge_amount,
                    "remaining_balance": round(balance, 2),
                    "anomaly": anomaly,
                })

    df = pd.DataFrame(rows)

    # --- Introduce light, realistic missingness in the sensor columns ----------
    rng_np = np.random.default_rng(SEED)
    for col, frac in [("temperature", 0.012), ("humidity", 0.012), ("fan_usage_hours", 0.006)]:
        mask = rng_np.random(len(df)) < frac
        df.loc[mask, col] = np.nan

    return df


def main() -> None:
    print(f"Generating ~{TARGET_ROWS:,} rows for {N_METERS} meters x {N_DAYS} days...")
    df = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

    anomalies = int(df["anomaly"].sum())
    outages = int(df["power_outage"].sum())
    print(f"Wrote {len(df):,} rows -> {OUT_PATH}")
    print(f"  Meters: {df['meter_id'].nunique()} | Anomalies: {anomalies} "
          f"({anomalies / len(df) * 100:.2f}%) | Outage hours: {outages}")
    print(f"  Mean hourly kWh: {df['units_consumed_kwh'].mean():.3f} | "
          f"Missing temp readings: {int(df['temperature'].isna().sum())}")


if __name__ == "__main__":
    main()
