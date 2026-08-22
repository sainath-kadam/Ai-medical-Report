"""Analysis job persistence (CONTRACTS.md §4/§7/§12).

Standard `BaseRepository` CRUD (table `analysis_jobs`) — no extra methods needed.
`AnalysisService` drives a job through its status transitions (`queued` -> `preprocessing`
-> `analyzing` -> `generating_report` -> `completed`/`failed`) using the inherited
`list_scoped`/`update_scoped`/`find_by_id_scoped` directly, and the
`GET /analysis/jobs/{jobId}` / `GET /analysis/studies/{id}/jobs` routes read the same
table through this repository so `GET /jobs/{id}` always reflects live progress.
"""

from __future__ import annotations

from app.database.models import AnalysisJob
from app.repositories.base import BaseRepository


class AnalysisJobRepository(BaseRepository):
    model = AnalysisJob
