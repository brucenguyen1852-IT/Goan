import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.database import get_db
from app.deps import get_current_user, get_driver_profile
from app.domains.escrow import service as escrow_service
from app.domains.escrow.models import EscrowTransaction
from app.domains.escrow.schemas import EscrowSummary, EscrowTransactionOut, RefundRequestResponse
from app.domains.users import repository as users_repo
from app.domains.users.models import DriverProfile, User

router = APIRouter(prefix="/drivers", tags=["escrow"])


@router.get("/me/escrow", response_model=EscrowSummary)
async def my_escrow(
    profile: DriverProfile = Depends(get_driver_profile), db: AsyncSession = Depends(get_db)
) -> EscrowSummary:
    stmt = (
        select(EscrowTransaction)
        .where(EscrowTransaction.driver_id == profile.user_id)
        .order_by(EscrowTransaction.created_at.desc())
        .limit(100)
    )
    txs = (await db.execute(stmt)).scalars().all()
    return EscrowSummary(
        escrow_balance=profile.escrow_balance,
        escrow_target=profile.escrow_target,
        escrow_status=profile.escrow_status,
        refund_requested_at=profile.escrow_refund_requested_at,
        refund_scheduled_at=profile.escrow_refund_scheduled_at,
        transactions=[EscrowTransactionOut.model_validate(t) for t in txs],
    )


@router.post("/{driver_id}/escrow/request-refund", response_model=RefundRequestResponse)
async def request_refund(
    driver_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RefundRequestResponse:
    """Chỉ tài xế đó hoặc admin mới được yêu cầu hoàn ký quỹ (SPEC 8)."""
    if user.role is not UserRole.ADMIN and user.id != driver_id:
        raise PermissionDeniedError("Không có quyền với ký quỹ của tài xế khác")

    profile = await users_repo.get_driver_profile_by_user(db, driver_id)
    if profile is None:
        raise NotFoundError("Không tìm thấy hồ sơ tài xế")

    tx = await escrow_service.request_refund(db, profile)
    return RefundRequestResponse(amount=tx.amount, scheduled_payout_date=tx.scheduled_payout_date)
