"""Database engine/session helpers.

Production hedefi PostgreSQL'dir. Lokal geliştirme ve testte aynı SQLAlchemy
model katmanı SQLite URL'i ile de çalışabilir; bu production tercihini
değiştirmez, sadece geliştirme sürtünmesini azaltır.
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    configured = os.environ.get("DATABASE_URL", "").strip()
    return configured or "sqlite:///./.tandela_dev.db"


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def create_database_engine(url: Optional[str] = None) -> Engine:
    database_url = normalize_database_url(url or get_database_url())
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_database(engine: Optional[Engine] = None) -> None:
    from app.models import session_records  # noqa: F401

    Base.metadata.create_all(bind=engine or create_database_engine())
