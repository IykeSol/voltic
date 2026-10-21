"""Provide each meter's hourly usage as a DataFrame, derived from its profile."""

from __future__ import annotations

import pandas as pd

from app.config import settings
from app.services import profile_service
from app.services.synthetic import build_user_df


def load_meter_df(meter_id: str, days: int | None = None) -> pd.DataFrame:
    """Hourly usage for a meter, built from the user's profile. Empty if unset."""
    # Deplete the balance for real time elapsed before reading it.
    profile_service.settle_balance(meter_id)
    df = build_user_df(meter_id, days=30)
    if df.empty:
        return df
    if days is not None:
        cutoff = df["timestamp"].max() - pd.Timedelta(days=days)
        df = df[df["timestamp"] > cutoff].reset_index(drop=True)
    return df


def tariff_for(df: pd.DataFrame) -> float:
    """Naira-per-kWh tariff implied by the meter's income band."""
    if df.empty:
        return settings.DEFAULT_TARIFF
    income = str(df["income_level"].iloc[-1])
    return settings.TARIFF_BY_INCOME.get(income, settings.DEFAULT_TARIFF)
