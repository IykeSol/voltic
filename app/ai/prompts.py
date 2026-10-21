"""Prompt construction and a deterministic fallback for AI insights."""

from __future__ import annotations


def build_analysis_prompt(ctx: dict, focus: str | None = None) -> str:
    s = ctx["summary"]
    f = ctx["forecast"]
    appliances = ", ".join(
        f"{a['name']} {a['pct']}%" for a in ctx["appliances"]["appliances"][:4]
    )
    anomaly_count = ctx["anomalies"]["count"]
    focus_line = f'\nThe user specifically wants you to address: "{focus}".' if focus else ""

    return f"""You are an energy analyst embedded in a prepaid electricity dashboard for a
Nigerian household. Write a concise, practical analysis in plain professional
English. Do not use emojis. Do not invent dates, names, or figures beyond those
provided. Keep it grounded and specific.

Household & usage facts:
- Household size: {s['household_size']} people, income band: {s['income_level']}
- Average daily usage: {s['avg_daily_kwh']} kWh (about {s['total_month_kwh']} kWh in the last 30 days)
- Tariff: {s['tariff']} NGN/kWh, current balance: {s['remaining_balance']} NGN
- Peak usage hour: {s['peak_hour_label']}
- Weekday avg: {s['weekday_avg_kwh']} kWh vs weekend avg: {s['weekend_avg_kwh']} kWh
- Forecast tomorrow: {f['tomorrow_kwh']} kWh; next 7 days total: {f['next7_total_kwh']} kWh
- Estimated balance runs out around: {f['recharge_exhaustion_date']} (~{f['days_until_exhaustion']} days)
- Probability of an unusual spike soon: {int(f['spike_probability'] * 100)}%
- Likely appliance share: {appliances}
- Anomalies detected recently: {anomaly_count}{focus_line}

Respond in exactly these three short sections, each 2-3 sentences:
1. Consumption explanation
2. Risk assessment
3. Savings recommendation"""


def local_fallback(ctx: dict) -> str:
    """Readable analysis assembled from the numbers when Gemini is offline."""
    s = ctx["summary"]
    f = ctx["forecast"]
    apps = ctx["appliances"]["appliances"]
    top = apps[0]["name"] if apps else "general load"
    second = apps[1]["name"] if len(apps) > 1 else "lighting"
    spike = int(f["spike_probability"] * 100)
    anomalies = ctx["anomalies"]["count"]

    weekend = s.get("weekend_avg_kwh") or 0
    weekday = s.get("weekday_avg_kwh") or 0
    pattern = "higher on weekends" if weekend > weekday else "fairly steady across the week"

    return (
        "1. Consumption explanation\n"
        f"This {s['income_level']}-income household of {s['household_size']} uses about "
        f"{s['avg_daily_kwh']} kWh per day, peaking around {s['peak_hour_label']}. "
        f"{top} and {second} account for most of the load, and usage is {pattern}.\n\n"
        "2. Risk assessment\n"
        f"At the current rate the balance of {s['remaining_balance']:.0f} NGN should last until "
        f"about {f['recharge_exhaustion_date']} (~{f['days_until_exhaustion']} days). "
        f"The chance of an unusual spike in the near term is {spike}%, and "
        f"{anomalies} abnormal reading(s) were flagged recently.\n\n"
        "3. Savings recommendation\n"
        f"Shifting heavy appliance use away from the {s['peak_hour_label']} peak and trimming "
        f"{top.lower()} run-time would cut the daily {s['avg_daily_kwh']} kWh noticeably. "
        "Recharging in planned amounts rather than small frequent top-ups also avoids "
        "running dry unexpectedly."
    )
