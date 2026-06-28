"""Request auth context skeleton.

Gerçek login/JWT/RBAC henüz yok. Bu dependency API yüzeyine clinic/user
bağlamını bugünden taşır; production auth daha sonra aynı noktaya takılır.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel


class AuthContext(BaseModel):
    clinic_id: str
    user_id: str
    role: str = "dentist"


def get_auth_context(
    x_tandela_clinic_id: Optional[str] = Header(default=None),
    x_tandela_user_id: Optional[str] = Header(default=None),
    x_tandela_user_role: Optional[str] = Header(default=None),
) -> AuthContext:
    mode = os.environ.get("TANDELA_AUTH_MODE", "dev").strip().lower()
    clinic_id = (x_tandela_clinic_id or "").strip()
    user_id = (x_tandela_user_id or "").strip()
    role = (x_tandela_user_role or "dentist").strip() or "dentist"

    if mode == "required" and (not clinic_id or not user_id):
        raise HTTPException(status_code=401, detail="Clinic/user auth headers required.")

    return AuthContext(
        clinic_id=clinic_id or "dev-clinic",
        user_id=user_id or "dev-doctor",
        role=role,
    )
