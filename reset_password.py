"""
reset_password.py

Local dev utility: resets a user's password directly in the database.
Passwords are bcrypt-hashed on the way in (see backend/auth.py) - there
is no way to recover or display an existing plaintext password, only
to set a new one. Run this yourself; the new password is typed here,
in your own terminal, and never leaves this machine.

Usage:
    python reset_password.py <username>
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from database import SessionLocal
from models import User
from auth import hash_password

if len(sys.argv) != 2:
    print("Usage: python reset_password.py <username>")
    sys.exit(1)

username = sys.argv[1]
db = SessionLocal()
user = db.query(User).filter(User.username == username).first()
if not user:
    print(f"No user named {username!r}.")
    sys.exit(1)

new_password = getpass.getpass(f"New password for {username!r}: ")
confirm = getpass.getpass("Confirm: ")
if new_password != confirm:
    print("Passwords didn't match - nothing changed.")
    sys.exit(1)
if not new_password:
    print("Password can't be empty - nothing changed.")
    sys.exit(1)

user.hashed_password = hash_password(new_password)
db.commit()
db.close()
print(f"Password for {username!r} updated.")
