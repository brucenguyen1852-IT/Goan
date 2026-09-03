"""Nghiệp vụ maker–checker.

Ba ràng buộc là toàn bộ giá trị của module này, mọi thứ khác chỉ là CRUD:

1. Người tạo **không được** là người duyệt. Kể cả super_admin.
2. Người duyệt phải có quyền *duyệt* của đúng loại đề nghị đó — có quyền tạo không có nghĩa
   là được duyệt.
3. Đề nghị quá hạn tự hết hiệu lực, không nằm chờ vô thời hạn.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import log_event
from app.domains.approvals.constants import PERMISSION_PAIRS, ApprovalKind, ApprovalStatus
from app.domains.approvals.models import ApprovalRequest
from app.domains.iam import service as iam_service
from app.domains.iam.models import StaffUser

logger = logging.getLogger("goan.approvals")


def _aware(moment: datetime) -> datetime:
    """SQLite trả datetime không có tzinfo; Postgres thì có. So sánh thẳng sẽ nổ TypeError."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def create(
    db: AsyncSession,
    *,
    kind: ApprovalKind,
    maker: StaffUser,
    reason: str,
    amount: Decimal | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    payload: dict | None = None,
) -> ApprovalRequest:
    maker_permission, _ = PERMISSION_PAIRS[kind]
    iam_service.assert_permission(maker, maker_permission)

    request = ApprovalRequest(
        kind=kind,
        requested_by=maker.id,
        reason=reason,
        amount=amount,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.APPROVAL_EXPIRE_HOURS),
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    log_event(
        logger,
        "approval_requested",
        approval_id=str(request.id),
        kind=kind.value,
        maker=str(maker.id),
        amount=str(amount) if amount is not None else None,
    )
    return request


async def get(db: AsyncSession, approval_id: uuid.UUID) -> ApprovalRequest:
    request = await db.get(ApprovalRequest, approval_id)
    if request is None:
        raise NotFoundError("Không tìm thấy đề nghị")
    return request


def _assert_decidable(request: ApprovalRequest, checker: StaffUser) -> None:
    if request.status is not ApprovalStatus.PENDING:
        raise ConflictError(
            f"Đề nghị đã ở trạng thái '{request.status.value}', không quyết định lại được",
            details={"status": request.status.value},
        )
    if _aware(request.expires_at) <= datetime.now(timezone.utc):
        raise ConflictError("Đề nghị đã quá hạn", details={"status": ApprovalStatus.EXPIRED.value})
    if request.requested_by == checker.id:
        # Ràng buộc cốt lõi. Đứng trước cả kiểm tra quyền: một người vừa tạo vừa duyệt thì
        # dù có đủ quyền cũng làm cơ chế này thành vô nghĩa.
        raise PermissionDeniedError(
            "Người tạo đề nghị không được tự duyệt",
            details={"rule": "maker_checker", "approval_id": str(request.id)},
        )
    _, checker_permission = PERMISSION_PAIRS[request.kind]
    iam_service.assert_permission(checker, checker_permission)


async def approve(
    db: AsyncSession, request: ApprovalRequest, checker: StaffUser, note: str | None = None
) -> ApprovalRequest:
    _assert_decidable(request, checker)
    request.status = ApprovalStatus.APPROVED
    request.decided_by = checker.id
    request.decided_at = datetime.now(timezone.utc)
    request.decision_note = note
    await db.commit()
    await db.refresh(request)
    log_event(
        logger,
        "approval_approved",
        approval_id=str(request.id),
        kind=request.kind.value,
        maker=str(request.requested_by),
        checker=str(checker.id),
    )
    return request


async def reject(
    db: AsyncSession, request: ApprovalRequest, checker: StaffUser, note: str | None = None
) -> ApprovalRequest:
    _assert_decidable(request, checker)
    request.status = ApprovalStatus.REJECTED
    request.decided_by = checker.id
    request.decided_at = datetime.now(timezone.utc)
    request.decision_note = note
    await db.commit()
    await db.refresh(request)
    log_event(logger, "approval_rejected", approval_id=str(request.id), checker=str(checker.id))
    return request


async def cancel(db: AsyncSession, request: ApprovalRequest, maker: StaffUser) -> ApprovalRequest:
    """Người tạo rút lại đề nghị của chính mình. Người khác thì không."""
    if request.requested_by != maker.id:
        raise PermissionDeniedError("Chỉ người tạo mới rút lại được đề nghị")
    if request.status is not ApprovalStatus.PENDING:
        raise ConflictError("Đề nghị đã được quyết định")
    request.status = ApprovalStatus.CANCELLED
    await db.commit()
    await db.refresh(request)
    return request


async def expire_due(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Job nền: đóng các đề nghị quá hạn còn treo. Trả về số dòng đã đóng."""
    moment = now or datetime.now(timezone.utc)
    stmt = select(ApprovalRequest).where(ApprovalRequest.status == ApprovalStatus.PENDING)
    expired = 0
    for request in (await db.execute(stmt)).scalars().all():
        if _aware(request.expires_at) <= moment:
            request.status = ApprovalStatus.EXPIRED
            expired += 1
    if expired:
        await db.commit()
        log_event(logger, "approvals_expired", count=expired)
    return expired
