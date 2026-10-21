"""AI analysis route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.ai import gemini_client
from app.models.schemas import AnalyzeRequest
from app.services import insight_service
from app.utils.security import get_current_user

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/analyze")
def analyze(req: AnalyzeRequest, user: dict = Depends(get_current_user)):
    return insight_service.analyze(user["meter_id"], focus=req.focus, user_id=user["id"])


@router.get("/status")
def status():
    return {"gemini_available": gemini_client.is_available()}
