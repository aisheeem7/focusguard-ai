"""
database.py

SQLAlchemy engine/session setup. Uses SQLite by default (single file,
zero setup) when running locally; set DATABASE_URL to a Postgres URL
when deployed online - no other file needs to change, since all queries
go through the ORM.
"""

import os
import re
from datetime import timezone

from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.types import TypeDecorator

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or "sqlite:///./app.db"
# Tolerate the forms a connection string is easily pasted in: Neon's
# "psql 'postgresql://...'" command, or the URL wrapped in quotes.
if DATABASE_URL.startswith("psql "):
    DATABASE_URL = DATABASE_URL[len("psql "):].strip()
DATABASE_URL = DATABASE_URL.strip("'\"")
if not DATABASE_URL.startswith(("sqlite", "postgres://", "postgresql://", "postgresql+")):
    raise SystemExit(
        "DATABASE_URL must be a PostgreSQL connection string starting with postgresql:// "
        "(copy it from your Neon project's Connect dialog)."
    )
# Some hosts hand out "postgres://..." URLs, which SQLAlchemy only accepts
# under the "postgresql://" name; and Neon's SQLAlchemy snippet names a
# specific driver ("postgresql+psycopg://", "+asyncpg"...). The app ships
# psycopg2, so any of these is normalised to plain "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = "postgresql://" + DATABASE_URL.split("://", 1)[1]
    # asyncpg-style "ssl=require" means "sslmode=require" to psycopg2.
    DATABASE_URL = re.sub(r"([?&])ssl=", r"\1sslmode=", DATABASE_URL)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # No connection-level settings on purpose: connection poolers (like
    # Neon's pooled endpoint) reject startup options. Times are made
    # explicit-UTC per value instead (UTCDateTime below), so the database's
    # own timezone setting never matters. Pre-ping drops connections a
    # hosted database closed while idle.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
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
        if value is None:
            return value
        if dialect.name == "postgresql":
            # Stated as UTC outright, so Postgres stores the right instant
            # whatever timezone the server or pooler session is set to.
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        if value.tzinfo is not None:
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
