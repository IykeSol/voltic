"""Meter profile routes: set up / edit your household + appliances, and recharge."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import ProfileRequest, RechargeRequest
from app.services import profile_service
from app.utils.security import get_current_user

router = APIRouter(tags=["profile"])


@router.get("/profile")
def get_profile(user: dict = Depends(get_current_user)):
    # Settle first so the returned balance reflects real elapsed time.
    profile_service.settle_balance(user["meter_id"])
    prof = profile_service.get_profile(user["meter_id"])
    if prof is None:
        return {"has_profile": False, "meter_id": user["meter_id"]}
    return {"has_profile": True, **prof}


@router.post("/profile", status_code=201)
def save_profile(req: ProfileRequest, user: dict = Depends(get_current_user)):
    prof = profile_service.upsert_profile(user["meter_id"], req.model_dump())
    return {"has_profile": True, **prof}


@router.post("/recharge")
def recharge(req: RechargeRequest, user: dict = Depends(get_current_user)):
    new_balance = profile_service.add_recharge(user["meter_id"], req.amount)
    if new_balance is None:
        raise HTTPException(status_code=400, detail="Set up your meter before recharging")
    return {"balance": new_balance, "amount": req.amount}
