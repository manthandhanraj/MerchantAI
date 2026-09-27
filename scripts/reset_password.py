"""Reset a built-in account's password.

Built-in accounts have no email service, so "forgot password" needs an
administrator. Run this on the machine that hosts MerchantAI:

    python scripts/reset_password.py --email riya@example.com

It asks for the new password twice without echoing it, and never prints it.
Only built-in accounts are affected; with Supabase, use the password-reset email
or the Supabase dashboard instead.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings  # noqa: E402
from backend.app.services import local_auth  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a built-in account's password.")
    parser.add_argument("--email", required=True, help="The account's email address.")
    args = parser.parse_args()

    if settings.resolved_auth_mode != "local":
        print(
            "This installation uses Supabase accounts. Reset passwords through the "
            "password-reset email or the Supabase dashboard.",
            file=sys.stderr,
        )
        return 1

    if args.email.strip().lower() == settings.demo_user_email.lower():
        print(
            "The demo account's password follows DEMO_PASSWORD and is restored "
            "automatically. Change DEMO_PASSWORD instead.",
            file=sys.stderr,
        )
        return 1

    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat it: ")
    if first != second:
        print("The two passwords do not match. Nothing was changed.", file=sys.stderr)
        return 1

    try:
        local_auth.set_password(args.email, first)
    except local_auth.LocalAuthError as exc:
        print(f"Not changed: {exc}", file=sys.stderr)
        return 1

    print(f"Password updated for {args.email.strip().lower()}. Existing sessions stay valid until they expire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
