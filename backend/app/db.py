"""Application database entry points.

`app.models.database` owns the implementation; this module exposes the stable
import path requested by the MVP architecture.
"""

from __future__ import annotations

from app.models.database import (
    Base,
    create_database_engine,
    create_session_factory,
    get_database_url,
    init_database,
    normalize_database_url,
)

engine = create_database_engine()
SessionLocal = create_session_factory(engine)

__all__ = [
    "Base",
    "SessionLocal",
    "create_database_engine",
    "create_session_factory",
    "engine",
    "get_database_url",
    "init_database",
    "normalize_database_url",
]
