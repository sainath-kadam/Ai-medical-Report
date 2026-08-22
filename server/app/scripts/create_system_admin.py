"""One-time bootstrap for the very first `system_admin` account (CONTRACTS.md §2a).

There is no self-service signup for this role on purpose — `POST /auth/signup` always
creates a brand-new organization + `org_admin`, and letting anyone grant themselves
platform-wide access would be a serious security hole. Once at least one system_admin
exists, further ones can be created normally via `POST /platform/system-admins`
(system_admin-only) instead of this script.

Usage (from `server/`, with the venv active):

    python -m app.scripts.create_system_admin --name "Ada Admin" --email ada@example.com

Prompts for a password if `--password` isn't given, so it never sits in shell history.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from app.core.security import hash_password
from app.database.connection import close_db_connection, connect_to_db, get_session_factory
from app.repositories.user_repository import UserRepository


async def _run(name: str, email: str, password: str) -> None:
    await connect_to_db()
    try:
        async with get_session_factory()() as session:
            users = UserRepository(session)
            if await users.find_by_email(email) is not None:
                print(f"A user with email {email!r} already exists — aborting.")
                return

            created = await users.insert(
                {
                    "name": name,
                    "email": email,
                    "passwordHash": hash_password(password),
                    "googleId": None,
                    "avatarUrl": None,
                    "role": "system_admin",
                    "organizationId": None,
                    "isActive": True,
                    "emailVerifiedAt": None,
                }
            )
            print(f"Created system_admin {created['_id']} ({email}). Log in at POST /auth/login as usual.")
    finally:
        await close_db_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--email", required=True, help="Login email")
    parser.add_argument("--password", help="Omit to be prompted (recommended — avoids shell history)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    asyncio.run(_run(args.name, args.email, password))


if __name__ == "__main__":
    main()
