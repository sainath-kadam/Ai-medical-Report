"""Business logic for the patients domain (CONTRACTS.md §4/§9/§12) — a NEW entity that did
not exist in the old Node app.

RBAC (CONTRACTS.md §3): org_admin/doctor may list/create/view/edit/delete patients in
their own organization. This is enforced by the router's dependencies; this service
assumes the caller has already been authorized and only needs
`current_user.organization_id` — never a client-supplied organization id.

`mrn` uniqueness is enforced by the unique constraint on `(organizationId, mrn)`
(`app/database/models.py::Patient`); `sqlalchemy.exc.IntegrityError` is translated to
`AppError.conflict` here rather than pre-checking with a separate query (avoids a
check-then-insert race).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import CurrentUser
from app.repositories.patient_repository import PatientRepository
from app.repositories.study_repository import StudyRepository
from app.schemas.common import PaginationParams
from app.schemas.patient import PatientCreateRequest, PatientUpdateRequest
from app.services.audit_service import AuditService
from app.utils.ids import new_id, to_public, to_public_list
from app.utils.response import paginated


def _mrn_conflict(mrn: str | None) -> AppError:
    return AppError.conflict(
        f"A patient with MRN '{mrn}' already exists in this organization" if mrn else
        "A patient with this MRN already exists in this organization",
        "PATIENT_MRN_TAKEN",
    )


class PatientService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PatientRepository(db)
        self.studies = StudyRepository(db)
        self.audit = AuditService(db)

    async def list_patients(self, current_user: CurrentUser, pagination: PaginationParams) -> dict[str, Any]:
        extra_filter: dict[str, Any] = {}
        if pagination.search:
            extra_filter["$or"] = [
                {"name": {"$regex": pagination.search, "$options": "i"}},
                {"mrn": {"$regex": pagination.search, "$options": "i"}},
            ]
        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.repo.list_scoped(
            current_user.organization_id,
            extra_filter,
            sort=[("createdAt", -1)],
            skip=skip,
            limit=pagination.page_size,
        )
        return paginated(to_public_list(items), pagination.page, pagination.page_size, total)

    async def _next_generated_mrn(self, organization_id: str, offset: int = 0) -> str:
        """`MRN-` + zero-padded (patients in this org + 1 + offset). Sequential and readable
        like a real hospital number, and unique per organization by virtue of the DB
        constraint the caller retries against."""
        _, total = await self.repo.list_scoped(organization_id, {}, sort=[("createdAt", -1)], skip=0, limit=1)
        return f"MRN-{total + 1 + offset:06d}"

    async def create_patient(
        self,
        current_user: CurrentUser,
        payload: PatientCreateRequest,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        # No MRN supplied -> assign the next per-organization number (`MRN-000123`). The
        # unique constraint on (organizationId, mrn) is the arbiter: if two patients are
        # created at the same instant (or a hospital already used that number manually),
        # the insert fails and we simply move to the next number — only a caller-supplied
        # MRN that collides is reported back as a conflict.
        supplied_mrn = (payload.mrn or "").strip() or None
        attempt = 0
        while True:
            mrn = supplied_mrn or await self._next_generated_mrn(current_user.organization_id, offset=attempt)
            doc = {
                "_id": new_id(),
                "organizationId": current_user.organization_id,
                "mrn": mrn,
                "name": payload.name,
                "dateOfBirth": payload.date_of_birth.isoformat(),
                "sex": payload.sex,
                "contactPhone": payload.contact_phone,
                "contactEmail": payload.contact_email,
                "createdBy": current_user.id,
            }
            try:
                created = await self.repo.insert(doc)
                break
            except IntegrityError as exc:
                await self.db.rollback()
                if supplied_mrn or attempt >= 5:
                    raise _mrn_conflict(mrn) from exc
                attempt += 1

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="PATIENT_CREATED",
            resource_type="patient",
            resource_id=created["_id"],
            ip=ip,
            user_agent=user_agent,
        )
        return to_public(created)

    async def get_patient(self, current_user: CurrentUser, patient_id: str) -> dict[str, Any]:
        doc = await self.repo.find_by_id_scoped(patient_id, current_user.organization_id)
        if doc is None:
            raise AppError.not_found("Patient not found")
        return to_public(doc)

    async def update_patient(
        self,
        current_user: CurrentUser,
        patient_id: str,
        payload: PatientUpdateRequest,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        existing = await self.repo.find_by_id_scoped(patient_id, current_user.organization_id)
        if existing is None:
            raise AppError.not_found("Patient not found")

        update: dict[str, Any] = {}
        if payload.mrn is not None:
            update["mrn"] = payload.mrn
        if payload.name is not None:
            update["name"] = payload.name
        if payload.date_of_birth is not None:
            update["dateOfBirth"] = payload.date_of_birth.isoformat()
        if payload.sex is not None:
            update["sex"] = payload.sex
        if payload.contact_phone is not None:
            update["contactPhone"] = payload.contact_phone
        if payload.contact_email is not None:
            update["contactEmail"] = payload.contact_email

        if not update:
            return to_public(existing)

        try:
            updated = await self.repo.update_scoped(patient_id, current_user.organization_id, update)
        except IntegrityError as exc:
            await self.db.rollback()
            raise _mrn_conflict(update.get("mrn")) from exc
        if updated is None:
            raise AppError.not_found("Patient not found")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="PATIENT_UPDATED",
            resource_type="patient",
            resource_id=patient_id,
            metadata={"fields": sorted(update.keys())},
            ip=ip,
            user_agent=user_agent,
        )
        return to_public(updated)

    async def delete_patient(
        self,
        current_user: CurrentUser,
        patient_id: str,
        *,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        existing = await self.repo.find_by_id_scoped(patient_id, current_user.organization_id)
        if existing is None:
            raise AppError.not_found("Patient not found")

        deleted = await self.repo.delete_scoped(patient_id, current_user.organization_id)
        if not deleted:
            raise AppError.not_found("Patient not found")

        await self.audit.log(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="PATIENT_DELETED",
            resource_type="patient",
            resource_id=patient_id,
            ip=ip,
            user_agent=user_agent,
        )

    async def get_patient_studies(
        self, current_user: CurrentUser, patient_id: str, pagination: PaginationParams
    ) -> dict[str, Any]:
        """GET /patients/{id}/studies — delegates to `StudyRepository.list_scoped`
        (CONTRACTS.md §11/§12) rather than duplicating study-listing logic here."""
        existing = await self.repo.find_by_id_scoped(patient_id, current_user.organization_id)
        if existing is None:
            raise AppError.not_found("Patient not found")

        skip = (pagination.page - 1) * pagination.page_size
        items, total = await self.studies.list_scoped(
            current_user.organization_id,
            {"patientId": patient_id},
            sort=[("createdAt", -1)],
            skip=skip,
            limit=pagination.page_size,
        )
        return paginated(to_public_list(items), pagination.page, pagination.page_size, total)
