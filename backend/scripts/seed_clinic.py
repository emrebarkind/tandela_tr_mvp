from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import hash_password
from app.db import SessionLocal, engine, init_database
from app.models.session_records import Clinic, User


def main() -> int:
    clinic_id = os.environ.get("SEED_CLINIC_ID", "test-clinic")
    clinic_name = os.environ.get("SEED_CLINIC_NAME", "Klinia Test Kliniği")
    user_id = os.environ.get("SEED_USER_ID", "test-dentist")
    email = os.environ.get("SEED_EMAIL", "dentist@test.klinia")
    password = os.environ.get("SEED_PASSWORD", "klinia-demo-123")

    init_database(engine)
    db = SessionLocal()
    try:
        clinic = db.get(Clinic, clinic_id)
        if clinic is None:
            clinic = Clinic(id=clinic_id, name=clinic_name)
            db.add(clinic)

        user = db.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                clinic_id=clinic_id,
                role="dentist",
                email=email,
                password_hash=hash_password(password),
            )
            db.add(user)
        else:
            user.clinic_id = clinic_id
            user.role = "dentist"
            user.email = email
            user.password_hash = hash_password(password)

        db.commit()
    finally:
        db.close()

    print(f"Seed hazır: clinic_id={clinic_id} email={email} password={password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
