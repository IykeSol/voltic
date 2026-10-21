"""Assembles the full analytical context and produces the AI narrative."""

from __future__ import annotations

import json
from datetime import datetime

from app.ai import gemini_client
from app.ai.prompts import build_analysis_prompt, local_fallback
from app.database.db import get_conn
from app.services import (
    analytics_service,
    anomaly_service,
    appliance_service,
    budget_service,
    forecast_service,
)


def build_context(meter_id: str) -> dict:
    return {
        "summary": analytics_service.get_summary(meter_id),
        "forecast": forecast_service.forecast(meter_id),
        "anomalies": anomaly_service.detect(meter_id),
        "appliances": appliance_service.breakdown(meter_id),
        "budget": budget_service.recommend(meter_id),
    }


def analyze(meter_id: str, focus: str | None = None, user_id: int | None = None) -> dict:
    ctx = build_context(meter_id)
    if not ctx["summary"].get("has_data"):
        return {"analysis": "No usage data is available for this meter yet.",
                "source": "none", "context": ctx}

    prompt = build_analysis_prompt(ctx, focus)
    text = gemini_client.generate(prompt)
    source = "gemini" if text else "local"
    if not text:
        text = local_fallback(ctx)

    result = {
        "analysis": text,
        "source": source,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "context": ctx,
    }

    if user_id is not None:
        _store_prediction(user_id, ctx, source)
    return result


def _store_prediction(user_id: int, ctx: dict, source: str) -> None:
    payload = json.dumps({
        "avg_daily_kwh": ctx["summary"].get("avg_daily_kwh"),
        "tomorrow_kwh": ctx["forecast"].get("tomorrow_kwh"),
        "exhaustion": ctx["forecast"].get("recharge_exhaustion_date"),
        "spike_probability": ctx["forecast"].get("spike_probability"),
        "source": source,
    })
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO predictions (user_id, created_at, payload) VALUES (?,?,?)",
            (user_id, datetime.utcnow().isoformat(), payload),
        )
