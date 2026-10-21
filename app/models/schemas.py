"""Pydantic request/response models for the API."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_INCOME = {"low", "middle", "high"}


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str) -> str:
        return v.strip().lower()


class UserPublic(BaseModel):
    id: int
    full_name: str
    email: str
    meter_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class AnalyzeRequest(BaseModel):
    # Optional free-text focus, e.g. "explain my night usage".
    focus: str | None = Field(default=None, max_length=300)


class ProfileRequest(BaseModel):
    """A user's household + appliance inputs and current prepaid balance."""

    household_size: int = Field(..., ge=1, le=30)
    income_level: str = Field(...)
    ac_hours: float = Field(0, ge=0, le=24)
    has_fridge: bool = True
    tv_hours: float = Field(0, ge=0, le=24)
    fan_hours: float = Field(0, ge=0, le=24)
    washer_loads: float = Field(0, ge=0, le=50)  # loads per week
    balance: float = Field(0, ge=0, le=10_000_000)

    @field_validator("income_level")
    @classmethod
    def _valid_income(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _INCOME:
            raise ValueError("income_level must be low, middle or high")
        return v


class RechargeRequest(BaseModel):
    amount: float = Field(..., gt=0, le=10_000_000)
