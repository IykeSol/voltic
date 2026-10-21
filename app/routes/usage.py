"""Usage analytics routes (all require a valid bearer token)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.services import (
    analytics_service,
    anomaly_service,
    appliance_service,
    budget_service,
    forecast_service,
)
from app.utils.security import get_current_user

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary")
def summary(user: dict = Depends(get_current_user)):
    return analytics_service.get_summary(user["meter_id"])


@router.get("/history")
def history(days: int = Query(30, ge=1, le=90), user: dict = Depends(get_current_user)):
    return analytics_service.get_history(user["meter_id"], days=days)


@router.get("/forecast")
def forecast(user: dict = Depends(get_current_user)):
    return forecast_service.forecast(user["meter_id"])


@router.get("/anomalies")
def anomalies(user: dict = Depends(get_current_user)):
    return anomaly_service.detect(user["meter_id"])


@router.get("/peak-hours")
def peak_hours(user: dict = Depends(get_current_user)):
    return analytics_service.get_peak_hours(user["meter_id"])


@router.get("/heatmap")
def heatmap(user: dict = Depends(get_current_user)):
    return analytics_service.get_heatmap(user["meter_id"])


@router.get("/trends")
def trends(user: dict = Depends(get_current_user)):
    return analytics_service.get_trends(user["meter_id"])


@router.get("/appliances")
def appliances(user: dict = Depends(get_current_user)):
    return appliance_service.breakdown(user["meter_id"])


@router.get("/budget")
def budget(user: dict = Depends(get_current_user)):
    return budget_service.recommend(user["meter_id"])
