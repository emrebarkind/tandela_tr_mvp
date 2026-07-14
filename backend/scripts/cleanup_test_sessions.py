"""Delete development/test sessions selected by explicit safe rules.

Development/test utility only. Do not run this against production data. The
script targets unlinked sessions and known test-like id prefixes. It defaults
to dry-run and always protects sessions linked to the reserved demo patients
``DEMO-001`` and ``DEMO-002``.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal, engine, init_database
from app.models.session_records import Patient, Session


SAFE_PREFIXES = (
    "golden-",
    "test-",
    "api-route-gate",
    "phase-b-loop",
    "audio-phase-c",
    "local-fdi-",
    "debug-chart-codex",
    "perio-test-",
    "perio-qa-",
    "stitch-perio-",
)
PROTECTED_DEMO_EXTERNAL_IDS = ("DEMO-001", "DEMO-002")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean unlinked and known test-prefix Tandela sessions.")
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help=(
            "Additional safe session id prefix filter. Repeatable. Without this option all known "
            "test prefixes are used. Unlinked sessions are always included."
        ),
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


def selection_reasons(session: Session, prefixes: list[str]) -> list[str]:
    reasons = []
    if session.patient_id is None:
        reasons.append("patient_id=null")
    reasons.extend(f"prefix:{prefix}" for prefix in prefixes if session.id.startswith(prefix))
    return reasons


def main() -> int:
    args = parse_args()
    prefixes = validate_prefixes(args.prefix)

    init_database(engine)
    db = SessionLocal()
    try:
        protected_patient_ids = set(
            db.scalars(select(Patient.id).where(Patient.external_id.in_(PROTECTED_DEMO_EXTERNAL_IDS)))
        )
        stmt = select(Session).order_by(Session.clinic_id, Session.started_at, Session.id)
        if args.clinic_id:
            stmt = stmt.where(Session.clinic_id == args.clinic_id)

        selected: list[tuple[Session, list[str]]] = []
        protected: list[tuple[Session, list[str]]] = []
        for session in db.scalars(stmt):
            reasons = selection_reasons(session, prefixes)
            if not reasons:
                continue
            target = protected if session.patient_id in protected_patient_ids else selected
            target.append((session, reasons))

        if not selected:
            print("Silinecek test/demo session bulunamadı.")
            if protected:
                print(f"Korunan demo session sayısı: {len(protected)}")
            return 0

        clinic_counts = Counter(session.clinic_id for session, _ in selected)
        reason_counts = Counter(reason for _, reasons in selected for reason in reasons)

        print("Dry-run hedef özeti:" if not args.execute else "Silme hedef özeti:")
        print(f"- Toplam benzersiz session: {len(selected)}")
        print(f"- Korunan demo session: {len(protected)}")
        print("- Klinik dağılımı:")
        for clinic_id, count in sorted(clinic_counts.items()):
            print(f"  - {clinic_id}: {count}")
        print("- Kategori eşleşmeleri (bir session birden fazla kurala uyabilir):")
        for reason, count in sorted(reason_counts.items()):
            print(f"  - {reason}: {count}")

        print("Hedef test/demo session'lar:")
        for session, reasons in selected:
            print(
                f"- {session.id} clinic={session.clinic_id} status={session.status} "
                f"patient_id={session.patient_id or 'null'} reasons={','.join(reasons)}"
            )

        if protected:
            print("Korunan demo session'lar (silinmeyecek):")
            for session, reasons in protected:
                print(
                    f"- {session.id} clinic={session.clinic_id} patient_id={session.patient_id} "
                    f"reasons={','.join(reasons)}"
                )

        if not args.execute:
            print(f"\nDry-run: {len(selected)} session silinmedi. Silmek için --execute ekleyin.")
            return 0

        for session, _ in selected:
            db.delete(session)
        db.commit()
        print(f"\nSilindi: {len(selected)} session ve bağlı draft/transcript/code/audit kayıtları.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
