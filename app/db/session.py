from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///private_market_insider_australia.db"


def get_database_url(explicit_url: str | None = None) -> str:
    return explicit_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine(database_url: str | None = None):
    url = get_database_url(database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, connect_args=connect_args)


def get_session_factory(database_url: str | None = None):
    return sessionmaker(bind=get_engine(database_url), autoflush=False, autocommit=False, future=True)


def get_session(database_url: str | None = None) -> Session:
    return get_session_factory(database_url)()

