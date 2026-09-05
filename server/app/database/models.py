"""SQLAlchemy table definitions (CONTRACTS.md §4 — one class per collection listed there).

Field lists match CONTRACTS.md §4 exactly; column names are the snake_case form of the
camelCase field name (`app/database/casing.py` converts between the two at the repository
boundary, so every service/route still reads/writes the same camelCase dict shape as before).

Two deliberate departures from a literal 1:1 field mapping:

- `studies.files` was an embedded array in Mongo. `app/api/uploads/routes.py`'s public
  file-download route looks up a study BY a file's `storageKey` alone (it doesn't know the
  study id yet) — that needs an indexed, queryable row, not a value buried inside a JSON
  blob. `StudyFile` is a real child table for exactly this reason; `StudyRepository` stitches
  it back onto a study dict as a `files` list so every caller sees the identical shape.
- Nested blobs that are always read/written whole and never queried by sub-field
  (`studies.lastFindings`, `report_templates.header/doctorInfo/sections/footer`,
  `reports.versions`, `audit_logs.metadata`) stay as JSON columns — splitting those into
  tables would add joins nothing in the app ever needs.

Timestamps: most `*At`/`*Date` fields were stored as plain ISO-8601 strings in Mongo (the
app itself calls `.isoformat()` before building the doc — see `auth_service.py`,
`study_service.py`, `analysis_service.py`) and nothing ever parses them back into a
date/datetime, so they stay `String` columns here to match exactly. `created_at`/
`updated_at` are the one upgrade to a native `DateTime` (correct sort/index semantics,
still handed back as an ISO string by `BaseRepository._to_dict`). `sessions.expires_at` /
`revoked_at` and `password_reset_tokens.expires_at` were already real datetimes in Mongo
(so the TTL index could act on them) and stay native `DateTime` here too — Postgres has no
TTL index equivalent, so an expired row just sits there until `find_valid`'s own
`expires_at > now()` filter excludes it; nothing currently sweeps/deletes them, matching
the fact that Mongo's TTL background reaper was a storage-layer detail no application code
ever depended on for correctness.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils.ids import new_id


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    address: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(500))
    plan: Mapped[str] = mapped_column(String(20), default="free")
    high_accuracy_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    report_header: Mapped[str | None] = mapped_column(Text)
    report_footer: Mapped[str | None] = mapped_column(Text)
    primary_color: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(32))
    # --- Subscription / trial (not in the original CONTRACTS.md shape) ---
    subscription_status: Mapped[str] = mapped_column(String(20), default="trial")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))
    # --- Platform-managed access (CONTRACTS.md §2c) — set only by a system_admin ---
    # A manual access period: the org is writable until this instant regardless of trial/
    # Stripe state (e.g. paid offline / by invoice). `None` = no manual period.
    access_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Hard block, orthogonal to the billing state (so lifting it restores whatever the
    # billing state is, with nothing to "remember"): while true, every write is refused
    # with 402 ORGANIZATION_SUSPENDED; reads and login keep working.
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    # Free-text note for the platform team only (e.g. invoice number). Never shown to the
    # organization's own users.
    access_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_id: Mapped[str | None] = mapped_column(String(255), index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    role: Mapped[str] = mapped_column(String(20))
    # Nullable ONLY for role="system_admin" (CONTRACTS.md §2a) — a platform-wide account
    # that isn't a member of any single tenant, unlike every other role. Every org-scoped
    # query still requires organization_id as a real string (see BaseRepository) — a
    # system_admin simply never calls those routes, by RBAC, not by a null-check.
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("organization_id", "mrn", name="uq_patients_org_mrn"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    mrn: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200), index=True)
    date_of_birth: Mapped[str] = mapped_column(String(40))
    sex: Mapped[str] = mapped_column(String(20))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    modality: Mapped[str] = mapped_column(String(20))
    body_part: Mapped[str] = mapped_column(String(200))
    clinical_history: Mapped[str | None] = mapped_column(Text)
    study_date: Mapped[str] = mapped_column(String(10))
    # The doctor who ORDERED the study (context shown on the report) -- distinct from
    # whoever ends up reporting/signing it (report_service.py's "Reported by", sourced
    # from the current user, not this field). Optional: not every referral is external.
    referring_physician: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), index=True)
    assigned_doctor_id: Mapped[str | None] = mapped_column(String(32))
    template_id: Mapped[str | None] = mapped_column(String(32))
    last_findings: Mapped[dict | None] = mapped_column(JSON)
    study_instance_uid: Mapped[str | None] = mapped_column(String(200))
    series_instance_uid: Mapped[str | None] = mapped_column(String(200))
    sop_instance_uid: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StudyFile(Base):
    """Child table for `studies.files` (CONTRACTS.md §4) — see this module's docstring for
    why this one nested list was split out instead of staying a JSON column."""

    __tablename__ = "study_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(32))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    provider: Mapped[str | None] = mapped_column(String(20))
    imaging_model: Mapped[str | None] = mapped_column(String(100))
    report_model: Mapped[str | None] = mapped_column(String(100))
    input_hash: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    header: Mapped[dict] = mapped_column(JSON)
    doctor_info: Mapped[dict] = mapped_column(JSON)
    sections: Mapped[list] = mapped_column(JSON)
    footer: Mapped[dict] = mapped_column(JSON)
    accent_color: Mapped[str] = mapped_column(String(20))
    style: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), index=True)
    template_id: Mapped[str | None] = mapped_column(String(32))
    versions: Mapped[list] = mapped_column(JSON)
    current_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    finalized_by: Mapped[str | None] = mapped_column(String(32))
    finalized_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(32))
    # Mapped attribute can't be named `metadata` — that name is reserved by SQLAlchemy's
    # DeclarativeBase for the table-metadata registry. The DB column is still `metadata`
    # (see `mapped_column("metadata", ...)`), which is what `BaseRepository` keys off of,
    # so callers still read/write a plain `metadata` key exactly as before.
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
