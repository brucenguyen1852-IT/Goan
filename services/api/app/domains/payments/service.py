"""Payments service (SPEC 9): thu tiền rider, ví tài xế (pending -> available), rút tiền, đối soát."""

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import (
    SETTLED_TRIP_STATUSES,
    EscrowTransactionType,
    PaymentMethod,
    PaymentStatus,
    WalletTransactionType,
)
from app.core.exceptions import AppError, ConflictError
from app.core.logging import log_event
from app.core.money import vnd
from app.domains.escrow.models import EscrowTransaction
from app.domains.payments.gateway import get_payment_gateway
from app.domains.payments.models import (
    DriverWallet,
    Payment,
    ReconciliationReport,
    WalletTransaction,
)
from app.domains.trips.models import Trip

logger = logging.getLogger("goan.payments")


async def get_or_create_wallet(db: AsyncSession, driver_id: uuid.UUID) -> DriverWallet:
    wallet = await db.get(DriverWallet, driver_id)
    if wallet is None:
        wallet = DriverWallet(driver_id=driver_id)
        db.add(wallet)
        await db.flush()
    return wallet


async def charge_trip(
    db: AsyncSession,
    trip: Trip,
    *,
    amount: Decimal,
    method: PaymentMethod = PaymentMethod.IN_APP_CARD,
    idempotency_key: str | None = None,
) -> Payment:
    """Thu tiền rider. Idempotent theo trip: nếu đã có payment completed thì trả lại (SPEC 13)."""
    existing = (
        await db.execute(
            select(Payment).where(
                Payment.trip_id == trip.id, Payment.status == PaymentStatus.COMPLETED
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if method is PaymentMethod.CASH_DISABLED:
        raise AppError("Không hỗ trợ tiền mặt")

    amount = vnd(amount)
    payment = Payment(
        trip_id=trip.id,
        rider_id=trip.rider_id,
        amount=amount,
        method=method,
        status=PaymentStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    await db.flush()

    result = await get_payment_gateway().charge(str(trip.rider_id), amount, str(trip.id))
    payment.status = PaymentStatus.COMPLETED if result.success else PaymentStatus.FAILED
    payment.gateway_reference = result.reference
    await db.flush()
    log_event(
        logger,
        "trip_charged",
        trip_id=str(trip.id),
        amount=str(amount),
        status=payment.status.value,
    )
    return payment


async def credit_driver_wallet(
    db: AsyncSession, driver_id: uuid.UUID, amount: Decimal, *, trip_id: uuid.UUID | None = None
) -> WalletTransaction:
    """Tiền vào pending_balance trước, giải phóng sau WALLET_HOLD_HOURS."""
    amount = vnd(amount)
    wallet = await get_or_create_wallet(db, driver_id)
    wallet.pending_balance = vnd(wallet.pending_balance + amount)
    tx = WalletTransaction(
        driver_id=driver_id,
        trip_id=trip_id,
        type=WalletTransactionType.TRIP_PAYOUT,
        amount=amount,
        available_at=datetime.now(timezone.utc) + timedelta(hours=settings.WALLET_HOLD_HOURS),
    )
    db.add(tx)
    await db.flush()
    return tx


async def release_pending_balances(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Celery beat: chuyển pending -> available khi hết thời gian giữ tiền."""
    now = now or datetime.now(timezone.utc)
    stmt = select(WalletTransaction).where(
        WalletTransaction.type == WalletTransactionType.TRIP_PAYOUT,
        WalletTransaction.released.is_(False),
        WalletTransaction.available_at <= now,
    )
    released = 0
    for tx in (await db.execute(stmt)).scalars().all():
        wallet = await get_or_create_wallet(db, tx.driver_id)
        wallet.pending_balance = vnd(wallet.pending_balance - tx.amount)
        wallet.available_balance = vnd(wallet.available_balance + tx.amount)
        tx.released = True
        released += 1
    await db.commit()
    log_event(logger, "wallet_pending_released", count=released)
    return released


async def withdraw(db: AsyncSession, driver_id: uuid.UUID, amount: Decimal) -> WalletTransaction:
    amount = vnd(amount)
    if amount <= 0:
        raise AppError("Số tiền rút phải lớn hơn 0")
    wallet = await get_or_create_wallet(db, driver_id)
    if wallet.available_balance < amount:
        raise ConflictError("Số dư khả dụng không đủ")

    wallet.available_balance = vnd(wallet.available_balance - amount)
    tx = WalletTransaction(
        driver_id=driver_id,
        type=WalletTransactionType.PAYOUT_WITHDRAWAL,
        amount=amount,
        released=True,
    )
    db.add(tx)
    await db.commit()
    log_event(logger, "wallet_withdrawn", driver_id=str(driver_id), amount=str(amount))
    return tx


async def run_daily_reconciliation(
    db: AsyncSession, report_date: date | None = None
) -> ReconciliationReport:
    """Đối soát ngày: fare vs payments, driver_payout vs wallet credit (SPEC 9.1)."""
    report_date = report_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    start = datetime.combine(report_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    trips_row = (
        await db.execute(
            select(
                func.count(Trip.id),
                func.coalesce(func.sum(Trip.final_fare), 0),
                func.coalesce(func.sum(Trip.driver_payout), 0),
            ).where(
                Trip.status.in_(SETTLED_TRIP_STATUSES),
                Trip.completed_at >= start,
                Trip.completed_at < end,
            )
        )
    ).one()
    total_trips, total_fare, total_payout = int(trips_row[0]), vnd(trips_row[1]), vnd(trips_row[2])

    total_payments = vnd(
        (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.created_at >= start,
                    Payment.created_at < end,
                )
            )
        ).scalar_one()
    )
    total_wallet_credit = vnd(
        (
            await db.execute(
                select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                    WalletTransaction.type == WalletTransactionType.TRIP_PAYOUT,
                    WalletTransaction.created_at >= start,
                    WalletTransaction.created_at < end,
                )
            )
        ).scalar_one()
    )
    total_escrow_accrual = vnd(
        (
            await db.execute(
                select(func.coalesce(func.sum(EscrowTransaction.amount), 0)).where(
                    EscrowTransaction.type == EscrowTransactionType.ACCRUAL,
                    EscrowTransaction.created_at >= start,
                    EscrowTransaction.created_at < end,
                )
            )
        ).scalar_one()
    )

    # Phí huỷ chuyến muộn cũng là tiền chạy qua hệ thống: khách trả, tài xế nhận. Chuyến bị
    # huỷ nên không có final_fare, nhưng bỏ khoản này ra ngoài thì đối soát sẽ luôn lệch
    # đúng bằng tổng phí huỷ trong ngày.
    total_cancellation_fee = vnd(
        (
            await db.execute(
                select(func.coalesce(func.sum(Trip.cancellation_fee), 0)).where(
                    Trip.cancellation_fee > 0,
                    Trip.cancelled_at >= start,
                    Trip.cancelled_at < end,
                )
            )
        ).scalar_one()
    )

    fare_diff = vnd(total_fare + total_cancellation_fee - total_payments)
    # Tiền vào ví = driver_payout - phần trích ký quỹ, cộng phí huỷ được trả thẳng cho tài xế.
    payout_diff = vnd(
        total_payout + total_cancellation_fee - total_wallet_credit - total_escrow_accrual
    )

    report = (
        await db.execute(
            select(ReconciliationReport).where(ReconciliationReport.report_date == report_date)
        )
    ).scalar_one_or_none() or ReconciliationReport(report_date=report_date)

    report.total_trips = total_trips
    report.total_final_fare = total_fare
    report.total_payments = total_payments
    report.total_driver_payout = total_payout
    report.total_wallet_credit = total_wallet_credit
    report.total_escrow_accrual = total_escrow_accrual
    report.total_cancellation_fee = total_cancellation_fee
    report.fare_payment_diff = fare_diff
    report.payout_wallet_diff = payout_diff
    report.balanced = fare_diff == 0 and payout_diff == 0
    report.details = {"window_start": start.isoformat(), "window_end": end.isoformat()}
    db.add(report)
    await db.commit()
    log_event(
        logger,
        "reconciliation_done",
        report_date=report_date.isoformat(),
        balanced=report.balanced,
        cancellation_fee=str(total_cancellation_fee),
    )
    return report
