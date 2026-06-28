from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


class AlembicMigrationTests(unittest.TestCase):
    def test_initial_migration_upgrades_and_downgrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "migration-test.db"
            config = Config("alembic.ini")

            with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}"}):
                command.upgrade(config, "head")

            engine = create_engine(f"sqlite:///{db_path}", future=True)
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertIn("sessions", tables)
                self.assertIn("transcripts", tables)
                self.assertIn("clinical_notes", tables)
                self.assertIn("review_decisions", tables)
                self.assertIn("export_payloads", tables)
                self.assertIn("audit_logs", tables)
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
