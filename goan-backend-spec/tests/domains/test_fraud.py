"""Fraud (SPEC 7): QR đơn ma, chạy vòng, tín hiệu thanh toán ngoài app, tráo tài xế."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.constants import FraudSeverity, FraudType, OnlineStatus, UserStatus
from app.core.exceptions import FraudRejectedError
from app.domains.fraud import service as fraud_service
from app.domains.fraud.models import FraudIncident
from tests.conftest import create_driver, create_rider, create_trip


# --- 7.1 Đơn ma ------------------------------------------------------------


def test_verify_qr_token_matching():
    assert fraud_service.verify_qr_token("abc123", "abc123") is True
    assert fraud_service.verify_qr_token("abc123", "wrong") is False
    assert fraud_service.verify_qr_token(None, "abc123") is False
    assert fraud_service.verify_qr_token("", "") is False


async def test_check_qr_verified_rejects_wrong_token(db):
    rider = await create_rider(db)
    driver_user, profile = await create_driver(db, qr_token="real-token")
    trip = await create_trip(db, rider, driver_user)

    with pytest.raises(FraudRejectedError):
        await fraud_service.check_qr_verified(db, trip, profile, "fake-token")


async def test_report_ghost_trip_bans_driver_and_locks_escrow(db):
    rider = await create_rider(db)
    driver_user, profile = await create_driver(db, escrow_balance=Decimal("500000"))
    trip = await create_trip(db, rider, driver_user)

    await fraud_service.report_ghost_trip(db, trip, profile, driver_user, reason="test")
    await db.commit()

    assert driver_user.status is UserStatus.BANNED
    assert profile.online_status is OnlineStatus.OFFLINE
    assert profile.active_qr_token is None
    incident = (await db.execute(select(FraudIncident))).scalars().first()
    assert incident.fraud_type is FraudType.GHOST_TRIP
    assert incident.severity is FraudSeverity.ACCOUNT_LOCKED


# --- 7.2 Chạy vòng ---------------------------------------------------------


def test_no_deviation_within_1_5x_optimal():
    result = fraud_service.evaluate_route_deviation(
        actual_distance_km=Decimal("14"),
        optimal_distance_km=Decimal("10"),
        per_km_rate=Decimal("20000"),
    )
    assert result.is_deviation is False
    assert result.billable_distance_km == Decimal("14")
    assert result.penalty_amount == Decimal("0")


def test_deviation_caps_billable_distance_and_penalizes_double():
    result = fraud_service.evaluate_route_deviation(
        actual_distance_km=Decimal("20"),
        optimal_distance_km=Decimal("10"),
        per_km_rate=Decimal("20000"),
    )
    assert result.is_deviation is True
    assert result.allowed_distance_km == Decimal("15.00")
    assert result.billable_distance_km == Decimal("15.00")
    assert result.excess_km == Decimal("5.00")
    # phạt = 5km × 20.000 × 2
    assert result.penalty_amount == Decimal("200000")


def test_deviation_without_optimal_distance_is_skipped():
    result = fraud_service.evaluate_route_deviation(
        actual_distance_km=Decimal("30"),
        optimal_distance_km=None,
        per_km_rate=Decimal("20000"),
    )
    assert result.is_deviation is False
    assert result.billable_distance_km == Decimal("30")


async def test_check_route_deviation_creates_incident_and_deducts_escrow(db):
    rider = await create_rider(db)
    driver_user, profile = await create_driver(db, escrow_balance=Decimal("1000000"))
    trip = await create_trip(db, rider, driver_user, optimal_distance_km=Decimal("10"))

    result = await fraud_service.check_route_deviation(
        db, trip, profile, actual_distance_km=Decimal("20"), per_km_rate=Decimal("20000")
    )
    await db.commit()

    assert result.is_deviation is True
    assert profile.escrow_balance == Decimal("800000")
    assert profile.fraud_strikes == 1
    incident = (await db.execute(select(FraudIncident))).scalars().first()
    assert incident.fraud_type is FraudType.ROUTE_DEVIATION
    assert incident.penalty_amount == Decimal("200000")


# --- 7.3 Thanh toán ngoài app ---------------------------------------------


def test_online_hours_per_trip_ratio():
    assert fraud_service.online_hours_per_trip(36000, 5) == 2.0  # 10h / 5 chuyến
    assert fraud_service.online_hours_per_trip(36000, 0) == 10.0


def test_anomalous_ratio_detection():
    assert fraud_service.is_anomalous_ratio(6.0, 2.0) is True
    assert fraud_service.is_anomalous_ratio(3.0, 2.0) is False
    assert fraud_service.is_anomalous_ratio(5.0, 0.0) is False


async def test_confirm_off_app_payment_warns_then_locks(db):
    rider = await create_rider(db)
    driver_user, profile = await create_driver(db)
    trip = await create_trip(db, rider, driver_user)

    for _ in range(2):
        incident = await fraud_service.confirm_off_app_payment(
            db, profile=profile, user=driver_user, trip=trip
        )
        assert incident.severity is FraudSeverity.WARNING
    assert driver_user.status is UserStatus.ACTIVE
    assert trip.insurance_voided is True  # rider mất quyền lợi bảo hiểm chuyến đó

    incident = await fraud_service.confirm_off_app_payment(
        db, profile=profile, user=driver_user, trip=trip
    )
    assert incident.severity is FraudSeverity.ACCOUNT_LOCKED
    assert driver_user.status is UserStatus.BANNED


# --- 7.4 Tráo tài xế ------------------------------------------------------


def test_selfie_threshold():
    assert fraud_service.is_selfie_match(0.85) is True
    assert fraud_service.is_selfie_match(0.84) is False


async def test_selfie_mismatch_bans_driver_immediately(db):
    driver_user, profile = await create_driver(db, escrow_balance=Decimal("2000000"))

    outcome = await fraud_service.verify_driver_selfie(
        db, driver_user, profile, "https://cdn.test/mismatch.jpg"
    )

    assert outcome.passed is False
    assert driver_user.status is UserStatus.BANNED
    assert profile.online_status is OnlineStatus.OFFLINE
    # Toàn bộ quỹ bị giữ lại chờ admin review, không tự động hoàn.
    assert profile.escrow_balance == Decimal("2000000")
    incident = (await db.execute(select(FraudIncident))).scalars().first()
    assert incident.fraud_type is FraudType.DRIVER_SWAP


async def test_selfie_match_keeps_driver_active(db):
    driver_user, profile = await create_driver(db)
    outcome = await fraud_service.verify_driver_selfie(
        db, driver_user, profile, "https://cdn.test/selfie-now.jpg"
    )
    assert outcome.passed is True
    assert driver_user.status is UserStatus.ACTIVE
    assert profile.next_selfie_check_at is not None
