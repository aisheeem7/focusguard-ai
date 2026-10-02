"""
conftest.py

Gives every test a fresh, isolated database and a FastAPI TestClient -
no real uvicorn server needed, tests run directly against the app in
memory. Each test gets its own clean database so tests can't interfere
with each other or with your real app.db.
"""

import os
import sys

# Point at a dedicated test database BEFORE importing anything that
# reads DATABASE_URL, and make sure the backend/ folder is importable
# regardless of where pytest is invoked from.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# TEST_DATABASE_URL runs the same suite against Postgres (the database
# used when deployed online); SQLite stays the default.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///./test_app.db")
# Linking an account normally starts the real window_tracker.py in the
# background - never from the test suite.
os.environ["FOCUSGUARD_AUTOSTART_TRACKER"] = "0"

if os.path.exists("test_app.db"):
    os.remove("test_app.db")

import pytest
from fastapi.testclient import TestClient

import main as main_module


@pytest.fixture()
def client():
    # Start each test with completely empty tables. Deliberately drop
    # and recreate tables on the SAME engine/connection pool rather than
    # deleting the underlying file mid-run - removing a SQLite file out
    # from under an already-open connection leaves stale file handles
    # and can cause spurious "readonly database" errors on some
    # filesystems.
    main_module.Base.metadata.drop_all(bind=main_module.engine)
    main_module.Base.metadata.create_all(bind=main_module.engine)

    with TestClient(main_module.app) as c:
        yield c


def register(client, username="alice", password="pass123"):
    r = client.post("/users/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def auth_headers(user: dict) -> dict:
    return {"Authorization": f"Bearer {user['api_token']}"}

