"""Standard `BaseRepository` for the `audit_logs` table (CONTRACTS.md §4).

Writes only ever go through `app.services.audit_service.AuditService.log(...)`, which
builds the exact documented row shape itself — this class exists mainly to give the
org-scoped read side (`GET /audit-logs`) a place to reuse `BaseRepository.list_scoped`
unchanged.
"""

from __future__ import annotations

from app.database.models import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository):
    model = AuditLog
