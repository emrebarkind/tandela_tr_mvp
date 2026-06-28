# Tandela TR data model

Current MVP persistence layer uses SQLAlchemy models under `backend/app/models/`.
Production target is PostgreSQL via `DATABASE_URL`; local development can use
SQLite with the same ORM models.

Schema changes are managed with Alembic under `backend/alembic/`.

Common commands from `backend/`:

```bash
python3 -m alembic upgrade head
python3 -m alembic downgrade -1
python3 -m alembic revision --autogenerate -m "describe change"
```

## MVP tables implemented

- `sessions`: anonymous clinical session envelope; optional `clinic_id` and
  `patient_ref`; current pipeline status/stage.
- `transcripts`: speaker-labelled transcript utterances as JSON. Raw audio is
  not stored here.
- `clinical_notes`: draft/approved clinical note JSON plus formatted note text.
- `review_decisions`: dentist approval decision, selected codes, reviewer id.
- `export_payloads`: copy/export-ready payload generated after dentist approval.
- `audit_logs`: session-scoped audit events for transcript save, AI note save,
  and manual review approval/rejection.

## Not yet implemented

- First-class `clinics`, `users`, `patients` tables and RBAC.
- Alembic migrations.
- Real code-source tables for TDB/SUT versioned procedure code data.
- Long-lived async job records backed by PostgreSQL/Redis.
- Encryption/key management and production backup/retention policies.
