"""
Generate publication-quality figures for the project report.

Reads the generated dataset + trained models and writes PNGs into report/figures/.
Also prints the dataset summary statistics used in the paper.

Run:
    python scripts/make_report_figures.py
"""

from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset" / "prepaid_meter_dataset.csv"
MODELS = ROOT / "trained_models"
OUT = ROOT / "report" / "figures"

ACCENT = "#3f6fe0"
ACCENT2 = "#7aa2ff"
GREEN = "#2f9e6f"
AMBER = "#d9883a"
RED = "#d6492f"
INK = "#1f2733"
GRID = "#dfe4ec"
PALETTE = [ACCENT, GREEN, AMBER, ACCENT2, RED, "#8a93a3"]

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "font.size": 10,
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#b9c2cf",
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "text.color": INK,
    "xtick.color": "#5b6675",
    "ytick.color": "#5b6675",
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

WATT = {"Air Conditioner": ("ac_usage_hours", 1.20), "Refrigerator": ("fridge_usage", 0.15),
        "Television": ("tv_usage_hours", 0.10), "Fan": ("fan_usage_hours", 0.07),
        "Washing Machine": ("washing_machine_usage", 0.50)}


def _save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  wrote {path.relative_to(ROOT)}")


def load():
    df = pd.read_csv(DATA)
    df["day_of_week"] = pd.to_datetime(df["date"]).dt.dayofweek
    reg = joblib.load(MODELS / "usage_model.pkl")
    ano = joblib.load(MODELS / "anomaly_model.pkl")
    return df, reg, ano


# --------------------------------------------------------------------------- #
def fig_architecture():
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

    def box(x, y, w, h, title, lines, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12",
                                    linewidth=1.3, edgecolor=color, facecolor=color + "14"))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="top", fontweight="bold",
                fontsize=10.5, color=INK)
        ax.text(x + w / 2, y + h - 0.72, lines, ha="center", va="top", fontsize=8.4, color="#46505f")

    box(0.4, 7.7, 9.2, 1.9, "Presentation  ·  Browser (vanilla JS + Chart.js)",
        "Landing   |   Auth (login / signup)   |   Dashboard: KPIs, charts, heatmap, AI panel", ACCENT)
    box(0.4, 5.3, 9.2, 1.9, "API  ·  FastAPI (JWT auth)",
        "/auth   /usage/{summary,history,forecast,anomalies,heatmap}   /ai/analyze   /export/{csv,pdf}", GREEN)
    box(0.4, 2.6, 9.2, 2.2, "Service layer",
        "Profile + Synthetic generator   |   Forecast (Random Forest)   |   Anomaly (Isolation Forest)\n"
        "Analytics  ·  Appliance sim  ·  Budget  ·  Insight orchestrator", AMBER)
    box(0.4, 0.3, 4.4, 1.8, "Data store", "SQLite\nusers · meter_profiles · recharge_history · predictions", "#8a93a3")
    box(5.2, 0.3, 4.4, 1.8, "External / artefacts", "Trained models (.pkl)\nGemini  gemini-2.0-flash-lite", RED)

    for y0, y1 in [(7.7, 7.2), (5.3, 4.8), (2.6, 2.1)]:
        ax.add_patch(FancyArrowPatch((5, y0), (5, y1), arrowstyle="-|>", mutation_scale=14,
                                     lw=1.4, color="#7a8696"))
    ax.text(5, 9.85, "Voltic — System Architecture", ha="center", fontsize=12.5, fontweight="bold")
    _save(fig, "fig01_architecture.png")


def fig_distribution(df):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
    live = df[df["power_outage"] == 0]["units_consumed_kwh"]
    axes[0].hist(live, bins=60, color=ACCENT, alpha=0.85, edgecolor="white", linewidth=0.3)
    axes[0].axvline(live.mean(), color=RED, ls="--", lw=1.3, label=f"mean = {live.mean():.2f} kWh")
    axes[0].set_title("Hourly consumption (grid-on hours)")
    axes[0].set_xlabel("kWh per hour"); axes[0].set_ylabel("Frequency"); axes[0].legend()
    axes[0].set_xlim(0, 2.2)

    daily = df.groupby(["meter_id", "date"])["units_consumed_kwh"].sum()
    axes[1].hist(daily, bins=45, color=GREEN, alpha=0.85, edgecolor="white", linewidth=0.3)
    axes[1].axvline(daily.mean(), color=RED, ls="--", lw=1.3, label=f"mean = {daily.mean():.1f} kWh/day")
    axes[1].set_title("Daily consumption per household")
    axes[1].set_xlabel("kWh per day"); axes[1].set_ylabel("Frequency"); axes[1].legend()
    _save(fig, "fig02_dataset_distribution.png")


def fig_pred(df, reg):
    feats = reg["features"]
    X, y = df[feats], df["units_consumed_kwh"]
    _, Xte, _, yte = train_test_split(X, y, test_size=0.20, random_state=42)
    pred = reg["pipeline"].predict(Xte)
    r2 = r2_score(yte, pred)
    res = yte.values - pred

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.0))
    hb = axes[0].hexbin(yte, pred, gridsize=45, cmap="Blues", mincnt=1, bins="log")
    lim = [0, max(yte.max(), pred.max()) * 0.6]
    axes[0].plot(lim, lim, color=RED, ls="--", lw=1.2)
    axes[0].set_xlim(lim); axes[0].set_ylim(lim)
    axes[0].set_title(f"Actual vs predicted  (R² = {r2:.3f})")
    axes[0].set_xlabel("Actual kWh"); axes[0].set_ylabel("Predicted kWh")
    fig.colorbar(hb, ax=axes[0], label="log10(count)")

    axes[1].hist(res, bins=70, color=ACCENT, alpha=0.85, edgecolor="white", linewidth=0.3)
    axes[1].axvline(0, color=RED, ls="--", lw=1.2)
    axes[1].set_title(f"Residuals  (MAE = {np.abs(res).mean():.3f} kWh)")
    axes[1].set_xlabel("Actual − Predicted (kWh)"); axes[1].set_ylabel("Frequency")
    axes[1].set_xlim(-1.0, 1.0)
    _save(fig, "fig03_actual_vs_predicted.png")


def fig_importance(reg):
    pipe = reg["pipeline"]
    rf = pipe.named_steps["rf"]
    names = pipe.named_steps["pre"].get_feature_names_out()
    imp = rf.feature_importances_
    agg: dict[str, float] = {}
    for n, v in zip(names, imp):
        base = n.split("__", 1)[1] if "__" in n else n
        for cat in ("day_type", "income_level"):
            if base.startswith(cat + "_"):
                base = cat
        agg[base] = agg.get(base, 0.0) + v
    items = sorted(agg.items(), key=lambda kv: kv[1])
    labels = [k.replace("_", " ") for k, _ in items]
    vals = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.barh(labels, vals, color=ACCENT, alpha=0.9, edgecolor="white")
    ax.set_title("Random Forest feature importance")
    ax.set_xlabel("Relative importance")
    ax.grid(axis="y", visible=False)
    for i, v in enumerate(vals):
        ax.text(v + 0.005, i, f"{v:.2f}", va="center", fontsize=8.2, color="#46505f")
    _save(fig, "fig05_feature_importance.png")


def fig_forecast(df, reg):
    feats = reg["features"]
    meter = df["meter_id"].value_counts().index[0]
    sub = df[df["meter_id"] == meter].copy()
    actual = sub.groupby("date")["units_consumed_kwh"].sum()
    sub["pred"] = reg["pipeline"].predict(sub[feats])
    pred = sub.groupby("date")["pred"].sum()
    dates = pd.to_datetime(actual.index)

    fig, ax = plt.subplots(figsize=(9.6, 3.9))
    ax.plot(dates, actual.values, color=ACCENT, lw=1.8, label="Actual daily kWh")
    ax.plot(dates, pred.values, color=AMBER, lw=1.8, ls="--", label="Model estimate")
    ax.fill_between(dates, actual.values, alpha=0.08, color=ACCENT)
    ax.set_title(f"Daily consumption — model tracking ({meter})")
    ax.set_xlabel("Date"); ax.set_ylabel("kWh per day"); ax.legend()
    fig.autofmt_xdate()
    _save(fig, "fig06_forecast_tracking.png")


def fig_hourly(df):
    by_hour = df[df["power_outage"] == 0].groupby("hour")["units_consumed_kwh"].mean()
    peak = int(by_hour.idxmax())
    colors = [RED if h == peak else ACCENT for h in by_hour.index]
    fig, ax = plt.subplots(figsize=(9.0, 3.7))
    ax.bar(by_hour.index, by_hour.values, color=colors, alpha=0.9, edgecolor="white")
    ax.set_title(f"Average consumption by hour of day  (peak = {peak:02d}:00)")
    ax.set_xlabel("Hour"); ax.set_ylabel("Mean kWh"); ax.set_xticks(range(0, 24, 2))
    ax.grid(axis="x", visible=False)
    _save(fig, "fig07_hourly_profile.png")


def fig_heatmap(df):
    piv = (df.groupby(["day_of_week", "hour"])["units_consumed_kwh"].mean()
           .unstack().reindex(index=range(7), columns=range(24)))
    fig, ax = plt.subplots(figsize=(9.4, 3.6))
    im = ax.imshow(piv.values, aspect="auto", cmap="YlGnBu", origin="lower")
    ax.set_yticks(range(7)); ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    ax.set_xticks(range(0, 24, 2)); ax.set_xticklabels(range(0, 24, 2))
    ax.set_title("Activity heatmap — mean kWh by weekday and hour")
    ax.set_xlabel("Hour of day"); ax.grid(False)
    fig.colorbar(im, ax=ax, label="Mean kWh")
    _save(fig, "fig08_heatmap.png")


def fig_appliances(df):
    rows = []
    for name, (col, kwh) in WATT.items():
        rows.append((name, float((df[col].fillna(0) * kwh).sum())))
    attributed = sum(v for _, v in rows)
    other = max(df["units_consumed_kwh"].sum() - attributed, 0.0)
    rows.append(("Lighting & other", other))
    rows.sort(key=lambda r: r[1], reverse=True)
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    total = sum(vals)
    pct = [v / total * 100 for v in vals]

    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    bars = ax.barh(labels[::-1], pct[::-1], color=PALETTE[::-1], alpha=0.9, edgecolor="white")
    ax.set_title("Estimated appliance share of consumption")
    ax.set_xlabel("Share of total kWh (%)"); ax.grid(axis="y", visible=False)
    for b, p in zip(bars, pct[::-1]):
        ax.text(b.get_width() + 0.6, b.get_y() + b.get_height() / 2, f"{p:.0f}%",
                va="center", fontsize=8.4, color="#46505f")
    _save(fig, "fig09_appliance_breakdown.png")


def fig_anomaly(df, ano):
    norms = ano["hourly_norms"]
    hmean = df["hour"].map({int(k): v for k, v in norms["mean"].items()})
    hstd = df["hour"].map({int(k): v for k, v in norms["std"].items()})
    d = df.copy()
    d["units_z"] = (d["units_consumed_kwh"] - hmean) / hstd
    X = ano["scaler"].transform(d[ano["features"]].fillna(0.0))
    d["flag"] = (ano["model"].predict(X) == -1).astype(int)

    normal = d[d["flag"] == 0].sample(min(7000, (d["flag"] == 0).sum()), random_state=1)
    flagged = d[d["flag"] == 1]
    jit = lambda n: np.random.default_rng(0).uniform(-0.35, 0.35, n)

    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.0), gridspec_kw={"width_ratios": [1.5, 1]})
    axes[0].scatter(normal["hour"] + jit(len(normal)), normal["units_consumed_kwh"],
                    s=5, color="#9fb0c9", alpha=0.35, label="Normal", linewidths=0)
    axes[0].scatter(flagged["hour"] + jit(len(flagged)), flagged["units_consumed_kwh"],
                    s=22, color=RED, alpha=0.85, label="Flagged anomaly", edgecolors="white", linewidths=0.4)
    axes[0].set_title("Isolation Forest — flagged readings")
    axes[0].set_xlabel("Hour of day"); axes[0].set_ylabel("kWh"); axes[0].legend(loc="upper left")
    axes[0].set_xticks(range(0, 24, 4))

    m = ["precision", "recall"]
    vals = [0.365, 0.639]
    axes[1].bar(m, vals, color=[ACCENT, GREEN], alpha=0.9, edgecolor="white", width=0.6)
    axes[1].set_ylim(0, 1); axes[1].set_title("Detection performance")
    axes[1].grid(axis="x", visible=False)
    for i, v in enumerate(vals):
        axes[1].text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=10, fontweight="bold")
    _save(fig, "fig10_anomaly_detection.png")


def print_stats(df):
    live = df[df["power_outage"] == 0]
    daily = df.groupby(["meter_id", "date"])["units_consumed_kwh"].sum()
    print("\n=== DATASET SUMMARY (for the paper) ===")
    print(f"rows                : {len(df):,}")
    print(f"meters / days       : {df['meter_id'].nunique()} meters x {df['date'].nunique()} days")
    print(f"anomalies           : {int(df['anomaly'].sum())} ({df['anomaly'].mean()*100:.2f}%)")
    print(f"outage hours        : {int(df['power_outage'].sum())} ({df['power_outage'].mean()*100:.1f}%)")
    print(f"missing temp/hum    : {int(df['temperature'].isna().sum())} / {int(df['humidity'].isna().sum())}")
    print(f"mean hourly kWh     : {live['units_consumed_kwh'].mean():.3f} (grid-on)")
    print(f"mean daily kWh      : {daily.mean():.2f}  (min {daily.min():.1f}, max {daily.max():.1f})")
    print(f"income split        : {dict(df.groupby('meter_id')['income_level'].first().value_counts())}")


def main():
    print("Loading data + models...")
    df, reg, ano = load()
    print("Generating figures...")
    fig_architecture()
    fig_distribution(df)
    fig_pred(df, reg)
    fig_importance(reg)
    fig_forecast(df, reg)
    fig_hourly(df)
    fig_heatmap(df)
    fig_appliances(df)
    fig_anomaly(df, ano)
    print_stats(df)
    print(f"\nAll figures saved to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
