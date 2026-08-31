import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import PermissionDeniedError
from app.database import get_db
from app.deps import get_current_admin, get_current_user, get_driver_profile
from app.domains.payments import service as payments_service
from app.domains.payments.models import ReconciliationReport, WalletTransaction
from app.domains.payments.schemas import (
    ReconciliationReportOut,
    WalletOut,
    WalletTransactionOut,
    WithdrawRequest,
    WithdrawResponse,
)
from app.domains.users.models import DriverProfile, User

router = APIRouter(tags=["payments"])


@router.get("/drivers/me/wallet", response_model=WalletOut)
async def my_wallet(
    profile: DriverProfile = Depends(get_driver_profile), db: AsyncSession = Depends(get_db)
) -> WalletOut:
    wallet = await payments_service.get_or_create_wallet(db, profile.user_id)
    await db.commit()
    return WalletOut(
        driver_id=wallet.driver_id,
        available_balance=wallet.available_balance,
        pending_balance=wallet.pending_balance,
        updated_at=wallet.updated_at,
    )


@router.get("/drivers/me/wallet/transactions", response_model=list[WalletTransactionOut])
async def my_wallet_transactions(
    profile: DriverProfile = Depends(get_driver_profile), db: AsyncSession = Depends(get_db)
) -> list[WalletTransactionOut]:
    stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.driver_id == profile.user_id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(100)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [WalletTransactionOut.model_validate(r) for r in rows]


@router.post("/drivers/{driver_id}/wallet/withdraw", response_model=WithdrawResponse)
async def withdraw(
    driver_id: uuid.UUID,
    payload: WithdrawRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WithdrawResponse:
    if user.role is not UserRole.ADMIN and user.id != driver_id:
        raise PermissionDeniedError("Không có quyền rút tiền của tài xế khác")
    await payments_service.withdraw(db, driver_id, payload.amount)
    wallet = await payments_service.get_or_create_wallet(db, driver_id)
    return WithdrawResponse(amount=payload.amount, available_balance=wallet.available_balance)


@router.get("/admin/reconciliation", response_model=list[ReconciliationReportOut])
async def list_reconciliation_reports(
    _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> list[ReconciliationReportOut]:
    stmt = select(ReconciliationReport).order_by(ReconciliationReport.report_date.desc()).limit(60)
    rows = (await db.execute(stmt)).scalars().all()
    return [ReconciliationReportOut.model_validate(r) for r in rows]


@router.post("/admin/reconciliation/run", response_model=ReconciliationReportOut)
async def run_reconciliation(
    report_date: date | None = None,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ReconciliationReportOut:
    report = await payments_service.run_daily_reconciliation(db, report_date)
    return ReconciliationReportOut.model_validate(report)
