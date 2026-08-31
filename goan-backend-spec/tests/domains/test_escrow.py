"""Escrow (SPEC 8): trích 15% payout, dừng khi đạt định mức, phạt cho phép âm số dư."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.constants import EscrowStatus, EscrowTransactionType, UserStatus
from app.core.exceptions import ConflictError
from app.domains.escrow import service as escrow_service
from app.domains.escrow.models import EscrowTransaction
from tests.conftest import create_driver


async def test_accrue_deducts_15_percent_of_driver_payout(db):
    _, profile = await create_driver(db)
    actual = await escrow_service.accrue(db, profile, Decimal("184440"))
    await db.commit()

    assert actual == Decimal("156774")  # 184.440 - 15%
    assert profile.escrow_balance == Decimal("27666")
    assert profile.escrow_status is EscrowStatus.ACCUMULATING

    tx = (await db.execute(select(EscrowTransaction))).scalar_one()
    assert tx.type is EscrowTransactionType.ACCRUAL
    assert tx.amount == Decimal("27666")
    assert tx.balance_after == Decimal("27666")


async def test_accrue_stops_at_target_and_marks_fulfilled(db):
    _, profile = await create_driver(db, escrow_balance=Decimal("2990000"))
    actual = await escrow_service.accrue(db, profile, Decimal("200000"))
    await db.commit()

    # Chỉ trích đủ phần còn thiếu 10.000đ, phần dư trả lại tài xế ngay.
    assert profile.escrow_balance == Decimal("3000000")
    assert profile.escrow_status is EscrowStatus.FULFILLED
    assert actual == Decimal("190000")


async def test_fulfilled_driver_receives_full_payout(db):
    _, profile = await create_driver(db, escrow_balance=Decimal("3000000"))
    profile.escrow_status = EscrowStatus.FULFILLED
    actual = await escrow_service.accrue(db, profile, Decimal("150000"))
    assert actual == Decimal("150000")
    assert profile.escrow_balance == Decimal("3000000")


async def test_penalize_allows_negative_balance_without_raising(db):
    _, profile = await create_driver(db, escrow_balance=Decimal("50000"))
    balance = await escrow_service.penalize(db, profile, Decimal("120000"), note="Phạt chạy vòng")
    await db.commit()

    assert balance == Decimal("-70000")
    assert profile.escrow_balance == Decimal("-70000")
    tx = (
        await db.execute(
            select(EscrowTransaction).where(
                EscrowTransaction.type == EscrowTransactionType.PENALTY_DEDUCTION
            )
        )
    ).scalar_one()
    assert tx.amount == Decimal("120000")


async def test_refund_requires_driver_to_stop_cooperating(db):
    user, profile = await create_driver(db, escrow_balance=Decimal("1000000"))
    profile.user = user
    with pytest.raises(ConflictError):
        await escrow_service.request_refund(db, profile)


async def test_refund_schedules_payout_after_delay(db):
    user, profile = await create_driver(db, escrow_balance=Decimal("1000000"))
    user.status = UserStatus.SUSPENDED
    profile.user = user
    await db.commit()

    tx = await escrow_service.request_refund(db, profile)
    assert tx.type is EscrowTransactionType.REFUND
    assert tx.scheduled_payout_date is not None
    assert profile.escrow_refund_requested_at is not None
    assert (tx.scheduled_payout_date - profile.escrow_refund_requested_at).days == 45
    assert profile.escrow_balance == Decimal("1000000")  # chỉ giảm khi thực chi

    processed = await escrow_service.process_due_refunds(
        db, now=tx.scheduled_payout_date
    )
    assert processed == 1
    assert profile.escrow_balance == Decimal("0")
