"""
database.py

SQLAlchemy engine/session setup. Uses SQLite by default (single file,
zero setup) when running locally; set DATABASE_URL to a Postgres URL
when deployed online - no other file needs to change, since all queries
go through the ORM.
"""

import os
from datetime import timezone

from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import TypeDecorator

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
# Some hosts hand out "postgres://..." URLs, which SQLAlchemy only accepts
# under the "postgresql://" name.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Session clock pinned to zero offset so naive UTC datetimes (what the
    # app uses everywhere) are stored and read back exactly, and date()
    # buckets by UTC day like SQLite does. "GMT" rather than "UTC" because
    # it's valid on every Postgres build, even ones without a timezone
    # database. Pre-ping drops connections a hosted database closed while idle.
    engine = create_engine(DATABASE_URL, connect_args={"options": "-c timezone=GMT"}, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UTCDateTime(TypeDecorator):
    """A timezone-aware column that always hands the app naive UTC
    datetimes - what SQLite returns natively, and what every
    `datetime.utcnow() - row.created_at` comparison in main.py expects.
    Postgres would otherwise return aware datetimes and those
    comparisons would raise."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


def get_db():
    """FastAPI dependency - yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
