"""Ví tài xế + đối soát (SPEC 9)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.constants import TripStatus
from app.core.exceptions import ConflictError
from app.domains.payments import service as payments_service
from app.domains.payments.models import DriverWallet, WalletTransaction
from tests.conftest import create_driver, create_rider, create_trip


async def test_credit_goes_to_pending_then_released_after_hold(db):
    driver_user, _ = await create_driver(db)
    await payments_service.credit_driver_wallet(db, driver_user.id, Decimal("150000"))
    await db.commit()

    wallet = await db.get(DriverWallet, driver_user.id)
    assert wallet.pending_balance == Decimal("150000")
    assert wallet.available_balance == Decimal("0")

    released = await payments_service.release_pending_balances(
        db, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    assert released == 1
    await db.refresh(wallet)
    assert wallet.pending_balance == Decimal("0")
    assert wallet.available_balance == Decimal("150000")


async def test_withdraw_requires_available_balance(db):
    driver_user, _ = await create_driver(db)
    await payments_service.credit_driver_wallet(db, driver_user.id, Decimal("100000"))
    await db.commit()

    with pytest.raises(ConflictError):
        await payments_service.withdraw(db, driver_user.id, Decimal("50000"))

    await payments_service.release_pending_balances(
        db, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    tx = await payments_service.withdraw(db, driver_user.id, Decimal("50000"))

    wallet = await db.get(DriverWallet, driver_user.id)
    assert tx.amount == Decimal("50000")
    assert wallet.available_balance == Decimal("50000")
    types = {t.type.value for t in (await db.execute(select(WalletTransaction))).scalars().all()}
    assert "payout_withdrawal" in types


async def test_charge_trip_is_idempotent_per_trip(db):
    rider = await create_rider(db)
    driver_user, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver_user)

    first = await payments_service.charge_trip(db, trip, amount=Decimal("250000"))
    second = await payments_service.charge_trip(db, trip, amount=Decimal("250000"))
    await db.commit()

    assert first.id == second.id


async def test_daily_reconciliation_reports_balanced_day(db):
    rider = await create_rider(db)
    driver_user, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver_user)
    trip.status = TripStatus.COMPLETED
    trip.completed_at = datetime.now(timezone.utc)
    trip.final_fare = Decimal("250000")
    trip.driver_payout = Decimal("145000")
    await db.commit()

    await payments_service.charge_trip(db, trip, amount=Decimal("250000"))
    await payments_service.credit_driver_wallet(
        db, driver_user.id, Decimal("145000"), trip_id=trip.id
    )
    await db.commit()

    report = await payments_service.run_daily_reconciliation(
        db, datetime.now(timezone.utc).date()
    )

    assert report.total_trips == 1
    assert report.total_final_fare == Decimal("250000")
    assert report.total_payments == Decimal("250000")
    assert report.fare_payment_diff == Decimal("0")
    assert report.payout_wallet_diff == Decimal("0")
    assert report.balanced is True
