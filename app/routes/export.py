"""Report export routes: CSV and PDF."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.services import report_service
from app.utils.security import get_current_user

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/csv")
def export_csv(user: dict = Depends(get_current_user)):
    data = report_service.build_csv(user["meter_id"])
    stamp = datetime.utcnow().strftime("%Y%m%d")
    filename = f"meter_{user['meter_id']}_{stamp}.csv"
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf")
def export_pdf(user: dict = Depends(get_current_user)):
    data = report_service.build_pdf(user["meter_id"], user["full_name"])
    stamp = datetime.utcnow().strftime("%Y%m%d")
    filename = f"meter_{user['meter_id']}_{stamp}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
