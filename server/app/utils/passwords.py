"""Shared password helpers.

`generate_temp_password` is used anywhere an account is created on someone else's behalf
with no SMTP configured to email them a link (CONTRACTS.md §2/§8) — the temporary
password is returned directly in that endpoint's response instead, once, for the inviter
to relay out-of-band. See `app/services/user_service.py::invite_user` and
`app/services/platform_service.py`.

`without_password_hash` is the one shared way `passwordHash` is stripped from a user dict
before it goes out over the wire (CONTRACTS.md §2) — used by every service that ever
returns a user document: `auth_service.py`, `user_service.py`, `platform_service.py`.
"""

from __future__ import annotations

import secrets
import string
from typing import Any

_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def generate_temp_password(length: int = 14) -> str:
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


def without_password_hash(user_doc: dict[str, Any]) -> dict[str, Any]:
    """Never let `passwordHash` leak into an API response (CONTRACTS.md §2). Safe to call
    on any user dict shape — a no-op if `passwordHash` isn't present."""
    clean = dict(user_doc)
    clean.pop("passwordHash", None)
    return clean
