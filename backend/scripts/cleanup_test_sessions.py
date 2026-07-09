"""Delete demo/test sessions by id prefix.

Development/test utility only. Do not run this against production data. The
script requires an explicit test-like prefix and defaults to dry-run so manual
demo sessions such as ``golden-s1-ui`` can be cleaned without touching real
clinic records by accident.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, engine, init_database
from app.models.session_records import Session


SAFE_PREFIXES = ("golden-", "test-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean development/test Tandela sessions by id prefix.")
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="Session id prefix to delete. Repeatable. Allowed defaults: golden-, test-.",
    )
    parser.add_argument(
        "--clinic-id",
        default=None,
        help="Optional clinic_id filter. Recommended when multiple clinics share the dev DB.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows. Without this flag the script only prints what would be deleted.",
    )
    return parser.parse_args()


def validate_prefixes(prefixes: list[str]) -> list[str]:
    effective = prefixes or list(SAFE_PREFIXES)
    unsafe = [prefix for prefix in effective if not any(prefix.startswith(safe) for safe in SAFE_PREFIXES)]
    if unsafe:
        raise SystemExit(
            "Unsafe prefix rejected. This script only deletes development/test prefixes: "
            f"{', '.join(SAFE_PREFIXES)}. Rejected: {', '.join(unsafe)}"
        )
    return effective


def main() -> int:
    args = parse_args()
    prefixes = validate_prefixes(args.prefix)

    init_database(engine)
    db = SessionLocal()
    try:
        stmt = select(Session).where(
            *[Session.id.startswith(prefix) for prefix in prefixes],
        )
        if len(prefixes) > 1:
            from sqlalchemy import or_

            stmt = select(Session).where(or_(*(Session.id.startswith(prefix) for prefix in prefixes)))
        if args.clinic_id:
            stmt = stmt.where(Session.clinic_id == args.clinic_id)

        sessions = list(db.scalars(stmt))
        if not sessions:
            print("Silinecek test/demo session bulunamadı.")
            return 0

        print("Hedef test/demo session'lar:")
        for session in sessions:
            print(f"- {session.id} clinic={session.clinic_id} status={session.status}")

        if not args.execute:
            print(f"\nDry-run: {len(sessions)} session silinmedi. Silmek için --execute ekleyin.")
            return 0

        for session in sessions:
            db.delete(session)
        db.commit()
        print(f"\nSilindi: {len(sessions)} session ve bağlı draft/transcript/code/audit kayıtları.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
