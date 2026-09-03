"""Luồng chuyến đi đầu-cuối ở tầng service (SPEC 5.2): QR -> chạy -> chốt tiền -> ví + ký quỹ."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.constants import PaymentStatus, TripStatus, UserStatus
from app.core.exceptions import ConflictError, FraudRejectedError
from app.domains.payments.models import DriverWallet, Payment, WalletTransaction
from app.domains.trips import repository as trips_repo
from app.domains.trips import service as trips_service
from tests.conftest import create_driver, create_rider, create_trip


async def _in_progress_trip(db, *, minutes_ago: int = 30):
    rider = await create_rider(db)
    driver_user, profile = await create_driver(db, qr_token="valid-qr")
    trip = await create_trip(
        db,
        rider,
        driver_user,
        status=TripStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        qr_verified=True,
        optimal_distance_km=Decimal("10"),
    )
    return rider, driver_user, profile, trip


async def test_verify_qr_moves_trip_to_in_progress(db):
    rider = await create_rider(db)
    driver_user, _ = await create_driver(db, qr_token="valid-qr")
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)

    trip = await trips_service.verify_qr(db, trip, rider, "valid-qr")

    assert trip.status is TripStatus.IN_PROGRESS
    assert trip.qr_verified_at is not None
    assert trip.started_at is not None


async def test_wrong_qr_keeps_trip_status(db):
    rider = await create_rider(db)
    driver_user, _ = await create_driver(db, qr_token="valid-qr")
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)

    with pytest.raises(FraudRejectedError):
        await trips_service.verify_qr(db, trip, rider, "hacked-qr")
    assert trip.status is TripStatus.DRIVER_ARRIVING


async def test_complete_without_qr_flags_ghost_trip(db):
    rider = await create_rider(db)
    driver_user, profile = await create_driver(db)
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)

    with pytest.raises(ConflictError):
        await trips_service.complete_trip(db, trip, driver_user)

    await db.refresh(driver_user)
    assert driver_user.status is UserStatus.BANNED


async def test_complete_trip_charges_rider_and_credits_wallet_after_escrow(db):
    _, driver_user, profile, trip = await _in_progress_trip(db, minutes_ago=30)
    # GPS log tạo quãng đường thực tế ~ tuyến tối ưu.
    now = datetime.now(timezone.utc)
    await trips_repo.add_gps_log(db, trip.id, 10.776, 106.700, now)
    await trips_repo.add_gps_log(db, trip.id, 10.800, 106.660, now)
    await db.commit()

    result = await trips_service.complete_trip(db, trip, driver_user)

    assert result.trip.status is TripStatus.COMPLETED
    assert result.fare.final_fare == trip.final_fare
    # Ký quỹ trích đúng 15% driver_payout.
    assert result.escrow_deducted == (result.fare.driver_payout * Decimal("0.15")).quantize(
        Decimal("1")
    )
    assert result.driver_actual_payout == result.fare.driver_payout - result.escrow_deducted
    assert profile.escrow_balance == result.escrow_deducted
    assert profile.total_trips == 1

    payment = (await db.execute(select(Payment))).scalar_one()
    assert payment.status is PaymentStatus.COMPLETED
    assert payment.amount == result.fare.final_fare

    wallet = await db.get(DriverWallet, driver_user.id)
    assert wallet.pending_balance == result.driver_actual_payout
    assert wallet.available_balance == Decimal("0")

    tx = (await db.execute(select(WalletTransaction))).scalar_one()
    assert tx.amount == result.driver_actual_payout
    assert tx.released is False


async def test_complete_trip_is_idempotent(db):
    _, driver_user, _, trip = await _in_progress_trip(db)
    first = await trips_service.complete_trip(db, trip, driver_user, idempotency_key="k1")
    second = await trips_service.complete_trip(db, trip, driver_user, idempotency_key="k1")

    assert second.trip.status is TripStatus.COMPLETED
    assert first.trip.final_fare == second.trip.final_fare
    payments = (await db.execute(select(Payment))).scalars().all()
    assert len(payments) == 1


async def test_complete_trip_caps_fare_when_route_deviation(db):
    _, driver_user, profile, trip = await _in_progress_trip(db)
    trip.optimal_distance_km = Decimal("2")  # thực tế ~4.8km -> vượt 1.5x
    await db.commit()

    now = datetime.now(timezone.utc)
    await trips_repo.add_gps_log(db, trip.id, 10.776, 106.700, now)
    await trips_repo.add_gps_log(db, trip.id, 10.800, 106.660, now)
    await db.commit()

    result = await trips_service.complete_trip(db, trip, driver_user)

    assert result.route_deviation_detected is True
    assert profile.fraud_strikes == 1
    # Cước chỉ tính tới optimal × 1.5 = 3km.
    assert result.fare.distance_fee == Decimal("3.00") * Decimal("20000")


async def test_rider_cancel_after_grace_period_charges_fee(db):
    rider = await create_rider(db)
    driver_user, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)
    trip.matched_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db.commit()

    trip = await trips_service.cancel_trip(db, trip, rider, reason="Đổi ý")

    assert trip.status is TripStatus.CANCELLED_BY_RIDER
    assert trip.cancellation_fee == Decimal("20000")
