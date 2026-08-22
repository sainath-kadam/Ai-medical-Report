"""Study persistence (CONTRACTS.md §4, §9, §12).

Standard `BaseRepository` CRUD (table `studies`) plus two cross-domain methods other
modules depend on by this EXACT name/signature (CONTRACTS.md §12):

- `add_file(study_id, organization_id, file_dict) -> dict | None` — called by the uploads
  domain after a file is written to storage, to record it and return the updated study.
- `set_last_findings(study_id, findings: dict) -> None` — called by `AnalysisService` (and
  the change-request flow) to persist the most recent imaging-analysis result on the study,
  so a formatting-only report revision can reuse it without re-running analysis.

`set_last_findings` intentionally does NOT take `organization_id` (matches the signature in
CONTRACTS.md §12 verbatim) — callers of it already hold a study they loaded (and therefore
already org-scope-validated) via `find_by_id_scoped` earlier in the same flow.

`files` was an embedded array in Mongo; it's a real child table here (`StudyFile`, see
`app/database/models.py`'s docstring for why) — every method that returns a study dict
attaches the current `files` list itself so callers see the exact same shape as before.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.database.models import Study, StudyFile
from app.repositories.base import BaseRepository
from app.utils.ids import new_id


def _file_to_dict(row: StudyFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "fileName": row.file_name,
        "storageKey": row.storage_key,
        "mimeType": row.mime_type,
        "sizeBytes": row.size_bytes,
        "uploadedBy": row.uploaded_by,
        "uploadedAt": row.uploaded_at.isoformat(),
    }


class StudyRepository(BaseRepository):
    model = Study

    async def _attach_files(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if doc is None:
            return None
        stmt = select(StudyFile).where(StudyFile.study_id == doc["_id"]).order_by(StudyFile.uploaded_at)
        rows = (await self.session.execute(stmt)).scalars().all()
        doc["files"] = [_file_to_dict(r) for r in rows]
        return doc

    async def find_by_id(self, doc_id: str) -> dict[str, Any] | None:
        return await self._attach_files(await super().find_by_id(doc_id))

    async def find_by_id_scoped(self, doc_id: str, organization_id: str) -> dict[str, Any] | None:
        return await self._attach_files(await super().find_by_id_scoped(doc_id, organization_id))

    async def list_scoped(
        self,
        organization_id: str,
        extra_filter: dict[str, Any] | None = None,
        *,
        sort: list[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        items, total = await super().list_scoped(organization_id, extra_filter, sort=sort, skip=skip, limit=limit)
        return [await self._attach_files(item) for item in items], total

    async def insert(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc = dict(doc)
        doc.pop("files", None)  # every study starts with no files; add_file() adds rows later
        created = await super().insert(doc)
        created["files"] = []
        return created

    async def update_scoped(self, doc_id: str, organization_id: str, update: dict[str, Any]) -> dict[str, Any] | None:
        update = dict(update)
        update.pop("files", None)
        return await self._attach_files(await super().update_scoped(doc_id, organization_id, update))

    async def find_ids_matching(
        self, organization_id: str, *, patient_id: str | None = None, modality: str | None = None
    ) -> list[str]:
        """Plain id lookup used by `ReportService.list_reports` to translate a
        patient/modality filter (on studies) into a `studyId in [...]` filter (on reports) —
        the SQL equivalent of the old `self.studies.collection.find(filter, {"_id": 1})`."""
        conditions = [Study.organization_id == organization_id]
        if patient_id:
            conditions.append(Study.patient_id == patient_id)
        if modality:
            conditions.append(Study.modality == modality)
        rows = (await self.session.execute(select(Study.id).where(*conditions))).scalars().all()
        return list(rows)

    async def find_file_by_storage_key(self, storage_key: str) -> dict[str, Any] | None:
        """Used by the public signed-URL download route (`app/api/uploads/routes.py`) for a
        best-effort content-type/filename lookup — the signed token itself is what actually
        authorizes the request, this is purely for response headers."""
        row = (
            await self.session.execute(select(StudyFile).where(StudyFile.storage_key == storage_key))
        ).scalar_one_or_none()
        return _file_to_dict(row) if row is not None else None

    async def add_file(
        self, study_id: str, organization_id: str, file_dict: dict[str, Any]
    ) -> dict[str, Any] | None:
        exists = (
            await self.session.execute(
                select(Study.id).where(Study.id == study_id, Study.organization_id == organization_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            return None

        self.session.add(
            StudyFile(
                id=file_dict.get("id") or new_id(),
                study_id=study_id,
                file_name=file_dict["fileName"],
                storage_key=file_dict["storageKey"],
                mime_type=file_dict["mimeType"],
                size_bytes=file_dict["sizeBytes"],
                uploaded_by=file_dict["uploadedBy"],
                uploaded_at=datetime.fromisoformat(file_dict["uploadedAt"]),
            )
        )
        await self.session.execute(
            update(Study).where(Study.id == study_id).values(updated_at=datetime.now(timezone.utc))
        )
        await self.session.commit()
        return await self.find_by_id_scoped(study_id, organization_id)

    async def set_last_findings(self, study_id: str, findings: dict[str, Any]) -> None:
        await self.session.execute(
            update(Study)
            .where(Study.id == study_id)
            .values(last_findings=findings, updated_at=datetime.now(timezone.utc))
        )
        await self.session.commit()
