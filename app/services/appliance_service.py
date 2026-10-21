"""Appliance simulation: attribute recent consumption to probable appliances."""

from __future__ import annotations

from app.services.data_access import load_meter_df

# kWh drawn per full hour of running - mirrors the dataset generator.
APPLIANCE_KWH = {
    "Air Conditioner": ("ac_usage_hours", 1.20),
    "Refrigerator": ("fridge_usage", 0.15),
    "Television": ("tv_usage_hours", 0.10),
    "Fan": ("fan_usage_hours", 0.07),
    "Washing Machine": ("washing_machine_usage", 0.50),
}


def breakdown(meter_id: str, days: int = 30) -> dict:
    df = load_meter_df(meter_id, days=days)
    if df.empty:
        return {"appliances": [], "total_kwh": 0}

    total = float(df["units_consumed_kwh"].sum())
    rows = []
    attributed = 0.0
    for name, (col, kwh) in APPLIANCE_KWH.items():
        est = float((df[col].fillna(0) * kwh).sum())
        attributed += est
        rows.append({"name": name, "kwh": round(est, 1)})

    # Whatever is left is lighting, phone charging, router, etc.
    other = max(total - attributed, 0.0)
    rows.append({"name": "Lighting & other", "kwh": round(other, 1)})

    for r in rows:
        r["pct"] = round(r["kwh"] / total * 100, 1) if total > 0 else 0
    rows.sort(key=lambda r: r["kwh"], reverse=True)

    return {"appliances": rows, "total_kwh": round(total, 1), "window_days": days}
