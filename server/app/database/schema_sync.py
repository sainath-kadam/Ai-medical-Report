"""Startup schema sync — the missing half of `Base.metadata.create_all`.

`create_all` creates tables that don't exist yet but never touches ones that do, so the
moment a column is added to an ORM model in `models.py` every existing deployment's
queries start failing with "column X does not exist" (that exact failure happened when
`studies.referring_physician` was added). Until this project adopts real migrations
(Alembic — see README.md's known gaps), `sync_missing_columns` closes that gap: after
`create_all`, it compares every model table with the live table and issues
`ALTER TABLE ... ADD COLUMN` for each column the model has and the database lacks.

Deliberately limited to the one change that is always safe to apply automatically —
adding a column that existing rows can satisfy (nullable, or with a server default). It
never drops or alters columns, never renames, never touches data, and refuses (with a loud
log line instead of a crash) to add a NOT NULL column without a default, because that
would fail against any table that already has rows. Anything beyond that needs a real
migration. Works on both Postgres (production) and SQLite (the test suite).
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateColumn

from app.core.logging import get_logger
from app.database.models import Base

logger = get_logger(__name__)


def sync_missing_columns(conn: Connection) -> list[str]:
    """Adds model columns missing from existing tables. Returns the `table.column` names it
    added. Meant to be called via `await conn.run_sync(sync_missing_columns)` right after
    `create_all` in the app's startup, inside the same transaction."""
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    preparer = conn.dialect.identifier_preparer
    added: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table: create_all just built it in full
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            if not column.nullable and column.server_default is None:
                logger.error(
                    "Schema drift: %s.%s is NOT NULL with no server default — cannot add it automatically; "
                    "write a migration (add it nullable / with a default, backfill, then tighten).",
                    table.name, column.name,
                )
                continue
            column_ddl = CreateColumn(column).compile(dialect=conn.dialect)
            conn.execute(text(f"ALTER TABLE {preparer.quote(table.name)} ADD COLUMN {column_ddl}"))
            added.append(f"{table.name}.{column.name}")
            logger.warning("Schema drift healed: added missing column %s.%s", table.name, column.name)

    return added
