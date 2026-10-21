"""
Evaluate the saved models against a held-out split and print a short report.

Run:
    python scripts/test_model.py
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "dataset" / "prepaid_meter_dataset.csv"
MODEL_DIR = ROOT / "trained_models"


def main() -> None:
    if not (MODEL_DIR / "usage_model.pkl").exists():
        raise SystemExit("Models not found. Run: python scripts/train_model.py")

    df = pd.read_csv(DATA_PATH)
    df["day_of_week"] = pd.to_datetime(df["date"]).dt.dayofweek

    # ---- Regression -------------------------------------------------------- #
    bundle = joblib.load(MODEL_DIR / "usage_model.pkl")
    pipeline, feats = bundle["pipeline"], bundle["features"]

    X, y = df[feats], df["units_consumed_kwh"]
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
    preds = pipeline.predict(X_test)

    mae = mean_absolute_error(y_test, preds)
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    r2 = r2_score(y_test, preds)

    print("=" * 52)
    print(" USAGE FORECASTING MODEL - held-out evaluation")
    print("=" * 52)
    print(f"  Test samples : {len(X_test):,}")
    print(f"  MAE          : {mae:.4f} kWh")
    print(f"  RMSE         : {rmse:.4f} kWh")
    print(f"  R2 score     : {r2:.4f}")
    verdict = "PASS (realistic 0.70-0.80 band)" if 0.70 <= r2 <= 0.82 else "outside target band"
    print(f"  Verdict      : {verdict}")

    print("\n  Sample predictions (actual -> predicted kWh):")
    sample = X_test.head(6).copy()
    sample_pred = pipeline.predict(sample)
    for actual, pred in zip(y_test.head(6).values, sample_pred):
        print(f"    {actual:6.3f}  ->  {pred:6.3f}")

    # ---- Anomaly detection ------------------------------------------------- #
    ab = joblib.load(MODEL_DIR / "anomaly_model.pkl")
    norms = ab["hourly_norms"]
    hmean = df["hour"].map({int(k): v for k, v in norms["mean"].items()})
    hstd = df["hour"].map({int(k): v for k, v in norms["std"].items()})
    df["units_z"] = (df["units_consumed_kwh"] - hmean) / hstd

    Xa = ab["scaler"].transform(df[ab["features"]].fillna(0.0))
    flags = (ab["model"].predict(Xa) == -1).astype(int)
    precision = precision_score(df["anomaly"], flags, zero_division=0)
    recall = recall_score(df["anomaly"], flags, zero_division=0)

    print("\n" + "=" * 52)
    print(" ANOMALY DETECTION MODEL")
    print("=" * 52)
    print(f"  Injected anomalies : {int(df['anomaly'].sum())}")
    print(f"  Flagged readings   : {int(flags.sum())}")
    print(f"  Precision          : {precision:.3f}")
    print(f"  Recall             : {recall:.3f}")


if __name__ == "__main__":
    main()
