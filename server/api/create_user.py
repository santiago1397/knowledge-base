"""Create (or reset) a login. Argon2id-hashes the password; no plaintext.

    uv run create_user.py            # prompts for email + password
    uv run create_user.py --email you@example.com
"""

from __future__ import annotations

import argparse
import getpass

from app.auth import hash_password
from app.db import cursor


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email")
    args = ap.parse_args()

    email = (args.email or input("Email: ")).strip().lower()
    pw = getpass.getpass("Password: ")
    if getpass.getpass("Confirm: ") != pw:
        print("Passwords do not match.")
        return 1
    if len(pw) < 10:
        print("Use at least 10 characters.")
        return 1

    with cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s,%s) "
            "ON CONFLICT (email) DO UPDATE SET password_hash=EXCLUDED.password_hash, "
            "failed_attempts=0, locked_until=NULL",
            (email, hash_password(pw)))
    print(f"User '{email}' ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
