"""camelCase (API/dict shape) <-> snake_case (SQL column name) conversion.

This is what lets every repository keep speaking the same camelCase, `_id`-keyed dict shape
the rest of the app already uses (CONTRACTS.md §1) while the actual Postgres columns stay
idiomatic snake_case — see `app/repositories/base.py`.
"""

from __future__ import annotations

import re

_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def camel_to_snake(name: str) -> str:
    if name == "_id":
        return "id"
    return _BOUNDARY.sub("_", name).lower()


def snake_to_camel(name: str) -> str:
    if name == "id":
        return "_id"
    first, *rest = name.split("_")
    return first + "".join(word.capitalize() for word in rest)
