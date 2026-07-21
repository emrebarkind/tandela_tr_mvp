"""Request auth context dependency."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel

from app.auth import AuthError, decode_access_token


class AuthContext(BaseModel):
    clinic_id: str
    user_id: str
    role: str = "dentist"


def get_auth_context(
    authorization: Optional[str] = Header(default=None),
    x_klinia_clinic_id: Optional[str] = Header(default=None),
    x_klinia_user_id: Optional[str] = Header(default=None),
    x_klinia_user_role: Optional[str] = Header(default=None),
) -> AuthContext:
    mode = os.environ.get("KLINIA_AUTH_MODE", "dev").strip().lower()
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Bearer token gerekli.")
        try:
            payload = decode_access_token(token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return AuthContext(
            clinic_id=str(payload["clinic_id"]),
            user_id=str(payload["sub"]),
            role=str(payload.get("role") or "dentist"),
        )

    clinic_id = (x_klinia_clinic_id or "").strip()
    user_id = (x_klinia_user_id or "").strip()
    role = (x_klinia_user_role or "dentist").strip() or "dentist"

    if mode in ("required", "jwt") and (not clinic_id or not user_id):
        raise HTTPException(status_code=401, detail="JWT Bearer token gerekli.")

    return AuthContext(
        clinic_id=clinic_id or "dev-clinic",
        user_id=user_id or "dev-doctor",
        role=role,
    )
