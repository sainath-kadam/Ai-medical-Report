"""Id generation and the `id`/`_id` dict-shape helper.

Design decision (see CONTRACTS.md §1 addendum): every id/reference field is a plain string
(`new_id()`), generated in application code rather than left to the database. Repositories
store rows keyed by this same string id and translate them back into API-shape dicts (with
`id` as the key, never a database-specific type) — `to_public`/`to_public_list` exist mainly
so call sites that historically expected a Mongo-style `_id` key can still normalize a dict
before it goes out over the wire.
"""

from __future__ import annotations

import uuid
from typing import Any


def new_id() -> str:
    return uuid.uuid4().hex


def to_public(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Rename `_id` -> `id` if present. Safe to call on `None` (common after a lookup miss)."""
    if doc is None:
        return None
    public = dict(doc)
    if "_id" in public:
        public["id"] = public.pop("_id")
    return public


def to_public_list(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [to_public(d) for d in docs if d is not None]
