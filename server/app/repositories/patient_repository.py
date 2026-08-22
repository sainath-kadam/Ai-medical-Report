"""Patient persistence (CONTRACTS.md §4, §12).

Per CONTRACTS.md §12: `app.repositories.patient_repository.PatientRepository(session)` is
"standard `BaseRepository` (table `patients`)" — nothing more. `mrn` uniqueness per
organization is enforced at the database level by the compound unique constraint
`(organization_id, mrn)` (`app/database/models.py`); it is `PatientService`'s job (not this
repository's) to catch the resulting `sqlalchemy.exc.IntegrityError` on insert/update and
translate it into `AppError.conflict` (CONTRACTS.md §1a — repositories stay thin
persistence helpers, services own the HTTP-facing error shape).
"""

from __future__ import annotations

from app.database.models import Patient
from app.repositories.base import BaseRepository


class PatientRepository(BaseRepository):
    model = Patient
