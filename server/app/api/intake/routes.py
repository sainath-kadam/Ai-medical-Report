"""Intake domain routes (CONTRACTS.md §9). One endpoint backing the frontend's
chat-style study intake flow (`ChatIntake`) — turns one free-text message into structured
patient/study fields. RBAC (CONTRACTS.md §3): same as creating a patient/study,
`org_admin`/`doctor` only. Stateless — the frontend resends `known` (whatever's been
confirmed so far in this conversation) with every message; nothing here is persisted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, require_admin_or_doctor
from app.schemas.intake import IntakeParseRequest
from app.services.intake_service import parse_intake
from app.utils.response import ok

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("/parse")
async def parse(payload: IntakeParseRequest, _current_user: CurrentUser = Depends(require_admin_or_doctor())):
    result = await parse_intake(payload)
    return ok(result)
