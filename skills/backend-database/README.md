# backend-database

`server/app/database/` — the SQLAlchemy (async) engine/session lifecycle plus the table
definitions every repository maps to. This is the bottom layer: repositories are the only
thing that should import from here directly (routes/services go through repositories).

## Key files

- `connection.py` — `connect_to_db()` / `close_db_connection()`, called once from the
  FastAPI lifespan in `app/main.py`. `get_session_factory()` hands out a fresh
  `AsyncSession` per request (an `AsyncSession` is NOT safe to share across requests,
  unlike the old Motor client this replaced); `app/api/deps.py::get_db` is the
  FastAPI-dependency wrapper every route uses to get one. `connect_to_db` does one throwaway
  connection at startup specifically so a bad `DATABASE_URL` fails fast at boot instead of on
  the first request.
- `casing.py` — `camel_to_snake` / `snake_to_camel`, the entire translation layer between
  the camelCase, `_id`-keyed dict shape the rest of the app speaks (CONTRACTS.md §1) and
  idiomatic snake_case Postgres columns. `_id` <-> `id` is special-cased in both directions.
- `models.py` — one `DeclarativeBase` subclass per table (`Organization`, `User`, `Patient`,
  `Study`, `StudyFile`, `AnalysisJob`, `ReportTemplate`, `Report`, `AuditLog`, `Notification`,
  `Session`, `PasswordResetToken`). Field lists match CONTRACTS.md §4. Every table's primary
  key is `id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)` —
  a plain app-generated string (`uuid4().hex`), never a DB-generated int/UUID type.

## Non-obvious things

- **`StudyFile` is a real child table, not a JSON column**, even though `studies.files` was
  an embedded array in the old Mongo shape. Reason: `app/api/uploads/routes.py`'s public
  file-download route looks up a study by a file's `storageKey` alone (it doesn't know the
  study id yet), which needs an indexed, queryable row. `StudyRepository` stitches the rows
  back onto a study dict as a `files` list so every caller still sees the same shape as
  before — see `backend-repositories`.
- **Most `*At`/`*Date` fields are plain `String` columns, not `DateTime`**, on purpose: in
  the old Mongo shape the app itself called `.isoformat()` before writing them and nothing
  ever parsed them back into a date/datetime, so they stay strings here to match exactly.
  Only `created_at`/`updated_at` (plus `sessions`/`password_reset_tokens`' `expires_at` /
  `revoked_at`, which were already real Mongo datetimes for TTL indexing) are native
  `DateTime` columns. Don't "fix" a `String` timestamp column to `DateTime` without checking
  whether something depends on the exact string format.
- **Expired session/reset-token rows are never swept** — Postgres has no TTL-index
  equivalent to what Mongo had, so an expired row just sits there until `find_valid`'s own
  `expires_at > now()` filter excludes it from results. This matches the old behavior (the
  Mongo TTL reaper was a storage-layer detail the application never depended on), it's not
  an oversight.
- `AuditLog.metadata_` is the Python attribute name for the `metadata` column — `metadata`
  itself is reserved by SQLAlchemy's `DeclarativeBase`. The column is still named `metadata`
  in Postgres (`mapped_column("metadata", ...)`), so `BaseRepository`'s generic camelCase
  dict translation still produces/accepts a plain `metadata` key exactly as every caller
  expects.
