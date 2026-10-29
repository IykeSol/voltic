"""Authentication routes: signup and login (JWT)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.database.db import assign_meter_for_new_user, get_conn
from app.models.schemas import LoginRequest, SignupRequest, TokenResponse, UserPublic
from app.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(row) -> TokenResponse:
    user = UserPublic(id=row["id"], full_name=row["full_name"],
                      email=row["email"], meter_id=row["meter_id"])
    token = create_access_token(row["id"], row["email"])
    return TokenResponse(access_token=token, user=user)


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(req: SignupRequest):
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (req.email,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="An account with this email already exists")

        meter_id = assign_meter_for_new_user(conn)
        conn.execute(
            """INSERT INTO users (full_name, email, password_hash, meter_id, created_at)
               VALUES (?,?,?,?,?)""",
            (req.full_name.strip(), req.email, hash_password(req.password),
             meter_id, datetime.utcnow().isoformat()),
        )
        row = conn.execute(
            "SELECT id, full_name, email, meter_id FROM users WHERE email = ?",
            (req.email,),
        ).fetchone()
    return _token_response(row)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, full_name, email, meter_id, password_hash FROM users WHERE email = ?",
            (req.email,),
        ).fetchone()
    if row is None or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _token_response(row)
