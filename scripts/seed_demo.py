"""Seed the shared read-only demo workspace.

With **built-in accounts** (no Supabase project) you do not need to run this:
the demo is created automatically the first time someone clicks "Try demo
account". Running it anyway pre-builds it so that first sign-in is instant.

With **Supabase**, run this once on a developer machine or a server — never in
the browser, and never as part of application startup. It needs
`SUPABASE_SERVICE_ROLE_KEY`, which bypasses Row Level Security and must stay in
the server environment.

    python scripts/seed_demo.py                 # create or refresh the demo
    python scripts/seed_demo.py --reset-password
    python scripts/seed_demo.py --force         # rebuild the analysis and report

What it creates
---------------
1. A real auth user (the demo signs in through normal authentication).
2. One merchant flagged `is_demo`.
3. Two uploads, taken from the committed synthetic dataset — the same data the
   public `/demo` dashboard has always used.
4. One completed analysis run.
5. One PDF report.

Everything is idempotent. Running it twice updates the same rows rather than
creating a second demo, and partial unique indexes in migration 0004 enforce
that at the database level too.

The seeded data is synthetic throughout. No real merchant, customer or payment
information is involved. The seeding logic itself lives in
`backend/app/services/demo_seed.py`, shared by both account systems.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings  # noqa: E402
from backend.app.services import demo_seed  # noqa: E402
from backend.app.services import workspace as ws  # noqa: E402
from backend.app.services.auth import AuthUser  # noqa: E402
from backend.app.services.supabase_client import (  # noqa: E402
    SupabaseError,
    admin_request,
    service_role_client,
)


def log(message: str) -> None:
    print(f"  {message}")


def fail(message: str) -> None:
    print("", file=sys.stderr)
    print(f"ERROR: {message}", file=sys.stderr)
    print("", file=sys.stderr)
    raise SystemExit(1)


# --------------------------------------------------------------------------
# Supabase auth user
# --------------------------------------------------------------------------
def find_user(email: str) -> dict | None:
    body = admin_request("GET", "/admin/users?page=1&per_page=200")
    users = (body or {}).get("users", []) if isinstance(body, dict) else []
    for user in users:
        if str(user.get("email", "")).lower() == email.lower():
            return user
    return None


def ensure_supabase_user(email: str, password: str, reset_password: bool) -> dict:
    existing = find_user(email)
    if existing:
        log(f"demo user already exists ({email})")
        if reset_password:
            admin_request("PUT", f"/admin/users/{existing['id']}", {"password": password})
            log("password reset to the configured value")
        return existing

    created = admin_request(
        "POST",
        "/admin/users",
        {
            "email": email,
            "password": password,
            # Confirmed on creation so the demo works even where email
            # confirmation is switched on for real sign-ups.
            "email_confirm": True,
            "user_metadata": {"full_name": "MerchantAI Demo"},
        },
    )
    if not created or not created.get("id"):
        fail("Supabase did not return a user id. Check SUPABASE_SERVICE_ROLE_KEY.")
    log(f"created demo user {email}")
    return created


def ensure_profile(client, user_id: str) -> None:
    if client.select(ws.PROFILES, filters={"id": f"eq.{user_id}"}, single=True) is None:
        client.insert(ws.PROFILES, {"id": user_id, "full_name": "MerchantAI Demo"})
        log("created profile")


# --------------------------------------------------------------------------
def seed_local(force: bool) -> int:
    print()
    print("MerchantAI — preparing the built-in demo account")
    print()
    try:
        demo_seed.ensure_local_demo(force=force)
    except demo_seed.SeedError as exc:
        fail(str(exc))
    print("Demo workspace ready.")
    print()
    print(f"  Email     {settings.demo_user_email}")
    print("  Password  (the value of DEMO_PASSWORD, shown on the login page)")
    print(f"  Stored in {settings.local_data_path}")
    print()
    return 0


def seed_supabase(email: str, password: str, reset_password: bool, force: bool) -> int:
    print()
    print("MerchantAI — seeding the Supabase demo workspace")
    print()

    if not settings.supabase_service_role_key:
        fail(
            "SUPABASE_SERVICE_ROLE_KEY must be set for seeding. It bypasses Row "
            "Level Security, so keep it in your local .env or the server "
            "environment, and never in any VITE_ variable."
        )
    if not settings.sales_path.exists():
        fail(f"The committed dataset is missing at {settings.sales_path}.")

    user_id = ""
    try:
        client = service_role_client()
        auth_user = ensure_supabase_user(email, password, reset_password)
        user_id = auth_user["id"]
        # The token carried here is the service-role key, which is how this
        # script reaches past RLS. It never leaves this process.
        user = AuthUser(id=user_id, email=email, role="authenticated", token=client.access_token)
        ensure_profile(client, user_id)
        demo_seed.seed_workspace(client, user, force=force, log=log)
    except (SupabaseError, ws.WorkspaceError, demo_seed.SeedError) as exc:
        fail(str(exc))

    print()
    print("Demo workspace ready.")
    print()
    print("  Add this to your BACKEND environment to make the demo read-only:")
    print(f"    DEMO_USER_ID={user_id}")
    print()
    print("  Add these to your FRONTEND environment to show the credentials:")
    print(f"    VITE_DEMO_EMAIL={email}")
    print("    VITE_DEMO_PASSWORD=<the same password>")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the read-only demo workspace.")
    parser.add_argument("--email", default=None, help="Demo account email (Supabase only).")
    parser.add_argument("--password", default=None, help="Demo account password (Supabase only).")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Set the demo password back to the configured value (Supabase).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Recompute the analysis and regenerate the report."
    )
    args = parser.parse_args()

    if settings.resolved_auth_mode == "local":
        return seed_local(args.force)

    return seed_supabase(
        args.email or settings.demo_user_email,
        args.password or settings.demo_password,
        args.reset_password,
        args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
