"""Anomaly detection over recent readings using the trained IsolationForest."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import settings
from app.services.data_access import load_meter_df


@lru_cache(maxsize=1)
def _load_model():
    import joblib

    path = settings.MODEL_DIR / "anomaly_model.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


def _classify(row: pd.Series, z: float) -> tuple[str, str, str]:
    """Return (severity, type, human message) for a flagged reading."""
    hour = int(row["hour"])
    if 0 <= hour <= 5 and z > 1.8:
        return ("high", "Night usage",
                "Unusually high consumption overnight - check for meter tampering "
                "or an appliance left running.")
    if z > 3.0:
        return ("high", "Consumption spike",
                "A sharp spike well above your normal level for this hour.")
    if row.get("fridge_usage", 0) > 0.9 and z > 1.5:
        return ("medium", "Appliance fault",
                "Sustained heavy draw consistent with a faulty fridge or AC compressor.")
    return ("medium", "Abnormal pattern",
            "Consumption deviates from your usual pattern for this time of day.")


def detect(meter_id: str, days: int = 21, limit: int = 25) -> dict:
    df = load_meter_df(meter_id, days=days)
    bundle = _load_model()
    if df.empty or bundle is None:
        return {"available": bundle is not None, "anomalies": [], "count": 0}

    norms = bundle["hourly_norms"]
    hmean = df["hour"].map({int(k): v for k, v in norms["mean"].items()})
    hstd = df["hour"].map({int(k): v for k, v in norms["std"].items()})
    df = df.copy()
    df["units_z"] = (df["units_consumed_kwh"] - hmean) / hstd
    df["expected"] = hmean

    X = bundle["scaler"].transform(df[bundle["features"]].fillna(0.0))
    df["flag"] = (bundle["model"].predict(X) == -1).astype(int)

    flagged = df[(df["flag"] == 1) & (df["units_z"] > 0)].copy()
    flagged = flagged.sort_values("timestamp", ascending=False).head(limit)

    items = []
    for _, row in flagged.iterrows():
        z = float(row["units_z"])
        severity, kind, message = _classify(row, z)
        expected = max(float(row["expected"]), 1e-3)
        items.append({
            "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "date": row["date"],
            "hour": int(row["hour"]),
            "units": round(float(row["units_consumed_kwh"]), 3),
            "expected": round(expected, 3),
            "deviation_pct": round((float(row["units_consumed_kwh"]) - expected) / expected * 100, 0),
            "severity": severity,
            "type": kind,
            "message": message,
        })

    return {"available": True, "anomalies": items, "count": len(items),
            "scanned_days": days}
