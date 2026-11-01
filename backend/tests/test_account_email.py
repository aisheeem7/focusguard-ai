"""
test_account_email.py

Forgot password, confirming an email address, and Sign in with Google.
No email is really sent and Google is never contacted: mailer.send_email
and the Google token check are swapped for fakes.
"""

import re

import pytest

import main as main_module
import mailer
from conftest import register, auth_headers


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "email_enabled", lambda: True)
    monkeypatch.setattr(mailer, "send_email", lambda to, subject, text: sent.append((to, subject, text)))
    return sent


def _token_from(email_text: str) -> str:
    return re.search(r"token=([\w-]+)", email_text).group(1)


def _confirm_email(client, user, email, outbox):
    r = client.patch("/users/me", json={"email": email}, headers=auth_headers(user))
    assert r.status_code == 200, r.text
    r = client.post("/auth/verify-email", json={"token": _token_from(outbox[-1][2])})
    assert r.status_code == 200, r.text


# ---- Confirming an email ----

def test_new_email_waits_for_confirmation(client, outbox):
    user = register(client, "alice", "pass123")
    r = client.patch("/users/me", json={"email": "Alice@Example.com"}, headers=auth_headers(user))
    assert r.json()["email"] is None
    assert r.json()["pending_email"] == "alice@example.com"
    assert outbox[-1][0] == "alice@example.com"

    r = client.post("/auth/verify-email", json={"token": _token_from(outbox[-1][2])})
    assert r.status_code == 200
    me = client.get("/users/me", headers=auth_headers(user)).json()
    assert me["email"] == "alice@example.com" and me["pending_email"] is None


def test_register_with_email_sends_confirmation(client, outbox):
    r = client.post("/users/register", json={"username": "bob", "password": "p", "email": "bob@example.com"})
    assert r.status_code == 201
    assert outbox[-1][0] == "bob@example.com"


def test_confirmation_link_works_once(client, outbox):
    user = register(client, "alice", "pass123")
    client.patch("/users/me", json={"email": "alice@example.com"}, headers=auth_headers(user))
    token = _token_from(outbox[-1][2])
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400


def test_cannot_claim_another_accounts_email(client, outbox):
    alice = register(client, "alice", "pass123")
    _confirm_email(client, alice, "shared@example.com", outbox)
    bob = register(client, "bob", "pass123")
    r = client.patch("/users/me", json={"email": "shared@example.com"}, headers=auth_headers(bob))
    assert r.status_code == 400


def test_bad_email_rejected(client, outbox):
    user = register(client, "alice", "pass123")
    r = client.patch("/users/me", json={"email": "not-an-email"}, headers=auth_headers(user))
    assert r.status_code == 400


def test_email_off_reports_503(client, monkeypatch):
    monkeypatch.setattr(mailer, "email_enabled", lambda: False)
    user = register(client, "alice", "pass123")
    assert client.patch("/users/me", json={"email": "a@example.com"}, headers=auth_headers(user)).status_code == 503
    assert client.post("/auth/forgot-password", json={"identifier": "alice"}).status_code == 503
    assert client.get("/auth/config").json()["email_enabled"] is False


# ---- Forgot password ----

def test_forgot_password_resets_and_signs_out_old_token(client, outbox):
    user = register(client, "alice", "oldpass")
    _confirm_email(client, user, "alice@example.com", outbox)

    r = client.post("/auth/forgot-password", json={"identifier": "alice@example.com"})
    assert r.status_code == 200
    assert outbox[-1][0] == "alice@example.com"

    r = client.post("/auth/reset-password", json={"token": _token_from(outbox[-1][2]), "new_password": "newpass"})
    assert r.status_code == 200
    assert r.json()["api_token"] != user["api_token"]
    assert client.get("/users/me", headers=auth_headers(user)).status_code == 401
    assert client.post("/users/login", json={"username": "alice", "password": "newpass"}).status_code == 200
    assert client.post("/users/login", json={"username": "alice", "password": "oldpass"}).status_code == 401


def test_forgot_password_gives_same_reply_for_unknown_users(client, outbox):
    register(client, "alice", "pass123")  # no confirmed email
    known = client.post("/auth/forgot-password", json={"identifier": "alice"})
    unknown = client.post("/auth/forgot-password", json={"identifier": "nobody"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert outbox == []


def test_reset_link_works_once(client, outbox):
    user = register(client, "alice", "pass123")
    _confirm_email(client, user, "alice@example.com", outbox)
    client.post("/auth/forgot-password", json={"identifier": "alice"})
    token = _token_from(outbox[-1][2])
    assert client.post("/auth/reset-password", json={"token": token, "new_password": "a"}).status_code == 200
    assert client.post("/auth/reset-password", json={"token": token, "new_password": "b"}).status_code == 400


def test_reset_emails_are_rate_limited(client, outbox):
    user = register(client, "alice", "pass123")
    _confirm_email(client, user, "alice@example.com", outbox)
    before = len(outbox)
    client.post("/auth/forgot-password", json={"identifier": "alice"})
    client.post("/auth/forgot-password", json={"identifier": "alice"})
    assert len(outbox) == before + 1


# ---- Sign in with Google ----

@pytest.fixture()
def google(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    claims = {"sub": "google-123", "email": "Carol@Gmail.com", "email_verified": True}
    monkeypatch.setattr(main_module, "_verify_google_credential", lambda credential, client_id: dict(claims))
    return claims


def test_google_sign_in_creates_then_reuses_account(client, google):
    first = client.post("/auth/google", json={"credential": "x"})
    assert first.status_code == 200
    assert first.json()["username"] == "carol"
    second = client.post("/auth/google", json={"credential": "x"})
    assert second.json()["user_id"] == first.json()["user_id"]
    me = client.get("/users/me", headers=auth_headers(first.json())).json()
    assert me["email"] == "carol@gmail.com" and me["google_linked"] is True


def test_google_sign_in_links_confirmed_email(client, google, outbox):
    user = register(client, "carol_k", "pass123")
    _confirm_email(client, user, "carol@gmail.com", outbox)
    r = client.post("/auth/google", json={"credential": "x"})
    assert r.json()["user_id"] == user["user_id"]


def test_google_sign_in_ignores_unconfirmed_email(client, google, outbox):
    # Someone typing Carol's address into their own profile mustn't get
    # her Google sign-in.
    squatter = register(client, "squatter", "pass123")
    client.patch("/users/me", json={"email": "carol@gmail.com"}, headers=auth_headers(squatter))
    r = client.post("/auth/google", json={"credential": "x"})
    assert r.json()["user_id"] != squatter["user_id"]


def test_google_username_avoids_taken_names(client, google):
    register(client, "carol", "pass123")
    r = client.post("/auth/google", json={"credential": "x"})
    assert r.json()["username"] == "carol2"


def test_google_sign_in_rejects_bad_token(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")

    def reject(credential, client_id):
        raise ValueError("bad token")

    monkeypatch.setattr(main_module, "_verify_google_credential", reject)
    assert client.post("/auth/google", json={"credential": "x"}).status_code == 401


def test_google_off_reports_503(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert client.post("/auth/google", json={"credential": "x"}).status_code == 503
    assert client.get("/auth/config").json()["google_client_id"] is None
