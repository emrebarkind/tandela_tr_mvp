from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


class AlembicMigrationTests(unittest.TestCase):
    def test_session_type_migration_backfills_existing_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "session-type-migration.db"
            database_url = f"sqlite:///{db_path}"
            config = Config("alembic.ini")

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "20260628_0001")

            engine = create_engine(database_url, future=True)
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO clinics (id, name, created_at) "
                            "VALUES ('clinic-old', 'Old Clinic', CURRENT_TIMESTAMP)"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO sessions "
                            "(id, clinic_id, status, started_at, created_at, updated_at) "
                            "VALUES ('session-old', 'clinic-old', 'draft', "
                            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        )
                    )
            finally:
                engine.dispose()

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "head")

            engine = create_engine(database_url, future=True)
            try:
                columns = {column["name"]: column for column in inspect(engine).get_columns("sessions")}
                self.assertIn("session_type", columns)
                self.assertFalse(columns["session_type"]["nullable"])
                with engine.connect() as connection:
                    session_type = connection.scalar(
                        text("SELECT session_type FROM sessions WHERE id='session-old'")
                    )
                self.assertEqual(session_type, "clinical_note")
            finally:
                engine.dispose()

    def test_initial_migration_upgrades_and_downgrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "migration-test.db"
            config = Config("alembic.ini")

            with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}"}):
                command.upgrade(config, "head")

            engine = create_engine(f"sqlite:///{db_path}", future=True)
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertIn("clinics", tables)
                self.assertIn("users", tables)
                self.assertIn("patients", tables)
                self.assertIn("patient_medical_histories", tables)
                self.assertIn("sessions", tables)
                self.assertIn("transcripts", tables)
                self.assertIn("clinical_notes", tables)
                self.assertIn("procedure_codes", tables)
                self.assertIn("code_suggestions", tables)
                self.assertIn("audit_logs", tables)
                patient_columns = {column["name"] for column in inspect(engine).get_columns("patients")}
                self.assertTrue({"national_id", "date_of_birth", "occupation", "address", "phone", "email", "referred_by"}.issubset(patient_columns))
            finally:
                engine.dispose()

            with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}"}):
                command.downgrade(config, "base")

            engine = create_engine(f"sqlite:///{db_path}", future=True)
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertNotIn("sessions", tables)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
