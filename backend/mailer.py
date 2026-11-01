"""
mailer.py

Sends FocusGuard's account emails (password reset, email confirmation)
from a Gmail account. Two ways to connect Gmail, set in .env / Render:

1. Gmail API (works everywhere, including Render's free plan, which
   blocks the normal email ports): GMAIL_ADDRESS, GOOGLE_CLIENT_ID,
   GOOGLE_CLIENT_SECRET and GMAIL_REFRESH_TOKEN. See DEPLOY.md for how to
   get the refresh token.
2. Gmail SMTP with an app password (simplest when running locally):
   GMAIL_ADDRESS and GMAIL_APP_PASSWORD.

With neither set, email is switched off and the sign-in page hides
"Forgot password?".
"""

import base64
import os
import smtplib
import sys
from email.message import EmailMessage

import httpx


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _uses_gmail_api() -> bool:
    return all(_env(n) for n in ("GMAIL_ADDRESS", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"))


def _uses_smtp() -> bool:
    return bool(_env("GMAIL_ADDRESS") and _env("GMAIL_APP_PASSWORD"))


def email_enabled() -> bool:
    return _uses_gmail_api() or _uses_smtp()


def _build_message(to: str, subject: str, text: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"FocusGuard AI <{_env('GMAIL_ADDRESS')}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    return msg


def _send_via_gmail_api(msg: EmailMessage) -> None:
    token = httpx.post("https://oauth2.googleapis.com/token", timeout=15, data={
        "client_id": _env("GOOGLE_CLIENT_ID"),
        "client_secret": _env("GOOGLE_CLIENT_SECRET"),
        "refresh_token": _env("GMAIL_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    })
    token.raise_for_status()
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    resp = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
        json={"raw": raw},
        timeout=15,
    )
    resp.raise_for_status()


def _send_via_smtp(msg: EmailMessage) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
        smtp.login(_env("GMAIL_ADDRESS"), _env("GMAIL_APP_PASSWORD").replace(" ", ""))
        smtp.send_message(msg)


def send_email(to: str, subject: str, text: str) -> None:
    """Sends one plain-text email. Runs as a background task after the
    response has gone out, so failures are logged rather than raised."""
    msg = _build_message(to, subject, text)
    try:
        if _uses_gmail_api():
            _send_via_gmail_api(msg)
        elif _uses_smtp():
            _send_via_smtp(msg)
        else:
            print(f"[warn] Email isn't set up - not sending {subject!r}", file=sys.stderr)
    except Exception as exc:
        print(f"[warn] Could not send {subject!r} email: {exc}", file=sys.stderr)
