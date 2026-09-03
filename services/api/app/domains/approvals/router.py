"""Router maker–checker cho Console."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_staff
from app.domains.approvals import service
from app.domains.approvals.constants import ApprovalKind, ApprovalStatus
from app.domains.approvals.models import ApprovalRequest
from app.domains.approvals.schemas import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalOut,
)
from app.domains.iam.models import StaffUser

router = APIRouter(prefix="/ops/approvals", tags=["ops-approvals"])


# Không dùng require_permission ở đây: quyền cần có phụ thuộc vào `kind` trong body, nên
# service kiểm tra sau khi đã biết loại đề nghị (xem PERMISSION_PAIRS).
@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreateRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ApprovalOut:
    request = await service.create(
        db,
        kind=body.kind,
        maker=staff,
        reason=body.reason,
        amount=body.amount,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        payload=body.payload,
    )
    return ApprovalOut.model_validate(request)


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    kind: ApprovalKind | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(get_current_staff),
) -> list[ApprovalOut]:
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    if kind:
        stmt = stmt.where(ApprovalRequest.kind == kind)
    rows = (await db.execute(stmt)).scalars().all()
    return [ApprovalOut.model_validate(r) for r in rows]


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(get_current_staff),
) -> ApprovalOut:
    return ApprovalOut.model_validate(await service.get(db, approval_id))


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ApprovalOut:
    request = await service.get(db, approval_id)
    return ApprovalOut.model_validate(await service.approve(db, request, staff, body.note))


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
async def reject_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ApprovalOut:
    request = await service.get(db, approval_id)
    return ApprovalOut.model_validate(await service.reject(db, request, staff, body.note))


@router.post("/{approval_id}/cancel", response_model=ApprovalOut)
async def cancel_approval(
    approval_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ApprovalOut:
    request = await service.get(db, approval_id)
    return ApprovalOut.model_validate(await service.cancel(db, request, staff))
