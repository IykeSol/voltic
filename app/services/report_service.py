"""CSV and PDF report generation."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from app.services import analytics_service, insight_service


def build_csv(meter_id: str) -> bytes:
    history = analytics_service.get_history(meter_id, days=90)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Units (kWh)", "Estimated Cost (NGN)"])
    for row in history["daily"]:
        writer.writerow([row["date"], row["kwh"], row["cost"]])

    writer.writerow([])
    writer.writerow(["Recharge Date", "Hour", "Amount (NGN)", "Balance After (NGN)"])
    for r in history["recharges"]:
        writer.writerow([r["date"], r["hour"], r["amount"], r["balance_after"]])

    return buf.getvalue().encode("utf-8")


def build_pdf(meter_id: str, user_name: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    result = insight_service.analyze(meter_id)
    ctx = result["context"]
    s, f = ctx["summary"], ctx["forecast"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18,
                                 textColor=colors.HexColor("#1f2937"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12,
                        textColor=colors.HexColor("#5b8cff"))
    body = styles["BodyText"]

    elements = [
        Paragraph("Prepaid Meter Usage Report", title_style),
        Paragraph(
            f"Meter {meter_id} &nbsp;|&nbsp; {user_name} &nbsp;|&nbsp; "
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            body,
        ),
        Spacer(1, 8 * mm),
        Paragraph("Summary", h2),
    ]

    table_data = [
        ["Metric", "Value"],
        ["Average daily usage", f"{s['avg_daily_kwh']} kWh"],
        ["Last 30 days total", f"{s['total_month_kwh']} kWh"],
        ["Remaining balance", f"NGN {s['remaining_balance']:.2f}"],
        ["Predicted exhaustion", f"{f['recharge_exhaustion_date']} (~{f['days_until_exhaustion']} days)"],
        ["Peak usage hour", s["peak_hour_label"]],
        ["Forecast tomorrow", f"{f['tomorrow_kwh']} kWh"],
        ["Spike probability", f"{int(f['spike_probability'] * 100)}%"],
    ]
    table = Table(table_data, colWidths=[70 * mm, 90 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5b8cff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7dce5")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements += [table, Spacer(1, 8 * mm), Paragraph("AI Insights", h2)]

    for para in result["analysis"].split("\n\n"):
        elements.append(Paragraph(para.replace("\n", "<br/>"), body))
        elements.append(Spacer(1, 3 * mm))

    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        f"<font size=8 color='#9aa4b2'>Insight source: {result['source']}. "
        "Figures are model estimates for guidance only.</font>", body))

    doc.build(elements)
    return buf.getvalue()
