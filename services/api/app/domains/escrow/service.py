"""Escrow service (SPEC 8) — ký quỹ luỹ tiến, tài xế không đóng tiền trước.

Các hàm ở đây KHÔNG commit: chúng chạy bên trong transaction của caller
(vd: hoàn tất chuyến) để đảm bảo rollback trọn vẹn khi có bước lỗi.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import EscrowStatus, EscrowTransactionType, UserStatus
from app.core.exceptions import ConflictError
from app.core.logging import log_event
from app.core.money import vnd
from app.domains.escrow.models import EscrowTransaction
from app.domains.users.models import DriverProfile

logger = logging.getLogger("goan.escrow")


async def accrue(
    db: AsyncSession,
    profile: DriverProfile,
    driver_payout: Decimal,
    *,
    trip_id: uuid.UUID | None = None,
) -> Decimal:
    """Trích 15% driver_payout vào quỹ cho tới khi đạt định mức.

    Trả về số tiền thực nhận (actual_payout) để cộng vào ví tài xế.
    """
    driver_payout = vnd(driver_payout)
    if profile.escrow_status is not EscrowStatus.ACCUMULATING:
        return driver_payout

    deduction = vnd(driver_payout * settings.ESCROW_ACCRUAL_RATE)
    # Không trích vượt định mức: phần dư trả lại cho tài xế ngay trong chuyến này.
    remaining_to_target = vnd(max(Decimal("0"), profile.escrow_target - profile.escrow_balance))
    deduction = min(deduction, remaining_to_target)
    if deduction <= 0:
        profile.escrow_status = EscrowStatus.FULFILLED
        return driver_payout

    profile.escrow_balance = vnd(profile.escrow_balance + deduction)
    if profile.escrow_balance >= profile.escrow_target:
        profile.escrow_status = EscrowStatus.FULFILLED

    db.add(
        EscrowTransaction(
            driver_id=profile.user_id,
            trip_id=trip_id,
            type=EscrowTransactionType.ACCRUAL,
            amount=deduction,
            balance_after=profile.escrow_balance,
            note="Trích 15% payout vào ký quỹ",
        )
    )
    await db.flush()
    log_event(
        logger,
        "escrow_accrued",
        driver_id=str(profile.user_id),
        amount=str(deduction),
        balance=str(profile.escrow_balance),
    )
    return vnd(driver_payout - deduction)


async def penalize(
    db: AsyncSession,
    profile: DriverProfile,
    amount: Decimal,
    *,
    note: str,
    trip_id: uuid.UUID | None = None,
) -> Decimal:
    """Trừ quỹ do gian lận. Cho phép âm số dư (ghi nhận công nợ), không raise (SPEC 8)."""
    amount = vnd(amount)
    if amount <= 0:
        return profile.escrow_balance

    profile.escrow_balance = vnd(profile.escrow_balance - amount)
    if profile.escrow_balance < profile.escrow_target:
        profile.escrow_status = EscrowStatus.ACCUMULATING

    db.add(
        EscrowTransaction(
            driver_id=profile.user_id,
            trip_id=trip_id,
            type=EscrowTransactionType.PENALTY_DEDUCTION,
            amount=amount,
            balance_after=profile.escrow_balance,
            note=note,
        )
    )
    await db.flush()
    log_event(
        logger,
        "escrow_penalized",
        driver_id=str(profile.user_id),
        amount=str(amount),
        balance=str(profile.escrow_balance),
    )
    return profile.escrow_balance


async def request_refund(db: AsyncSession, profile: DriverProfile) -> EscrowTransaction:
    """Hoàn quỹ chỉ khi tài xế ngưng hợp tác; giải ngân sau 45-60 ngày (SPEC 8)."""
    if profile.user.status is UserStatus.ACTIVE:
        raise ConflictError("Chỉ hoàn ký quỹ khi tài xế ngưng hợp tác (tài khoản không còn active)")
    if profile.escrow_refund_requested_at is not None:
        raise ConflictError("Đã có yêu cầu hoàn ký quỹ đang chờ xử lý")
    if profile.escrow_balance <= 0:
        raise ConflictError("Số dư ký quỹ không đủ để hoàn")

    now = datetime.now(timezone.utc)
    scheduled = now + timedelta(days=settings.ESCROW_REFUND_DELAY_DAYS)
    profile.escrow_refund_requested_at = now
    profile.escrow_refund_scheduled_at = scheduled

    tx = EscrowTransaction(
        driver_id=profile.user_id,
        type=EscrowTransactionType.REFUND,
        amount=profile.escrow_balance,
        balance_after=profile.escrow_balance,  # chỉ giảm khi thực sự chi trả
        note=f"Yêu cầu hoàn ký quỹ, dự kiến chi trả {scheduled.date().isoformat()}",
        scheduled_payout_date=scheduled,
    )
    db.add(tx)
    await db.commit()
    log_event(logger, "escrow_refund_requested", driver_id=str(profile.user_id))
    return tx


async def process_due_refunds(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Celery beat: chi trả các yêu cầu hoàn quỹ đã đến hạn."""
    now = now or datetime.now(timezone.utc)
    stmt = select(EscrowTransaction).where(
        EscrowTransaction.type == EscrowTransactionType.REFUND,
        EscrowTransaction.processed_at.is_(None),
        EscrowTransaction.scheduled_payout_date <= now,
    )
    processed = 0
    for tx in (await db.execute(stmt)).scalars().all():
        profile = (
            await db.execute(select(DriverProfile).where(DriverProfile.user_id == tx.driver_id))
        ).scalar_one_or_none()
        if profile is None:
            continue
        payout = min(tx.amount, profile.escrow_balance)
        profile.escrow_balance = vnd(profile.escrow_balance - payout)
        profile.escrow_refund_requested_at = None
        profile.escrow_refund_scheduled_at = None
        tx.amount = payout
        tx.balance_after = profile.escrow_balance
        tx.processed_at = now
        processed += 1
    await db.commit()
    return processed


async def lock_escrow_for_review(db: AsyncSession, profile: DriverProfile, reason: str) -> None:
    """Gian lận nghiêm trọng: giữ toàn bộ quỹ, không hoàn tự động (SPEC 7.4)."""
    profile.escrow_refund_requested_at = None
    profile.escrow_refund_scheduled_at = None
    db.add(
        EscrowTransaction(
            driver_id=profile.user_id,
            type=EscrowTransactionType.PENALTY_DEDUCTION,
            amount=Decimal("0"),
            balance_after=profile.escrow_balance,
            note=f"Giữ quỹ chờ admin review: {reason}",
        )
    )
    await db.flush()
