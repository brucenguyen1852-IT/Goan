"""Fraud service (SPEC 7) — 4 cơ chế: đơn ma, chạy vòng, thanh toán ngoài app, tráo tài xế.

Mỗi cơ chế là một hàm độc lập, phần tính toán thuần được tách ra để unit test không cần DB.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import (
    SETTLED_TRIP_STATUSES,
    FraudDetectedBy,
    FraudReviewStatus,
    FraudSeverity,
    FraudType,
    OnlineStatus,
    UserStatus,
)
from app.core.exceptions import FraudRejectedError
from app.core.logging import log_event
from app.core.money import vnd
from app.core.timeutil import ensure_utc
from app.domains.escrow import service as escrow_service
from app.domains.fraud.models import DriverOnlineSession, FraudIncident, FraudReviewQueue
from app.domains.trips.models import Trip
from app.domains.users.models import DriverProfile, User

logger = logging.getLogger("goan.fraud")


# --- 7.1 Đơn ma ------------------------------------------------------------


def verify_qr_token(expected_token: str | None, submitted_token: str) -> bool:
    """So khớp QR động của tài xế. Sai -> reject, KHÔNG chuyển trạng thái chuyến."""
    return bool(expected_token) and expected_token == submitted_token


async def check_qr_verified(
    db: AsyncSession, trip: Trip, profile: DriverProfile, submitted_token: str
) -> None:
    if not verify_qr_token(profile.active_qr_token, submitted_token):
        log_event(logger, "qr_verify_failed", trip_id=str(trip.id), driver_id=str(profile.user_id))
        raise FraudRejectedError("Mã QR không hợp lệ, không thể bắt đầu chuyến")


async def report_ghost_trip(
    db: AsyncSession, trip: Trip, profile: DriverProfile, user: User, reason: str
) -> FraudIncident:
    """Đơn ma đã xác nhận: khoá vĩnh viễn + giữ/trừ quỹ (SPEC 7.5)."""
    incident = FraudIncident(
        trip_id=trip.id,
        driver_id=profile.user_id,
        fraud_type=FraudType.GHOST_TRIP,
        detected_by=FraudDetectedBy.SYSTEM,
        severity=FraudSeverity.ACCOUNT_LOCKED,
        penalty_amount=Decimal("0"),
        details={"reason": reason, "trip_status": trip.status.value},
    )
    db.add(incident)
    user.status = UserStatus.BANNED
    profile.online_status = OnlineStatus.OFFLINE
    profile.active_qr_token = None
    profile.fraud_strikes += 1
    await escrow_service.lock_escrow_for_review(db, profile, reason="ghost_trip")
    await db.flush()
    log_event(logger, "fraud_ghost_trip", trip_id=str(trip.id), driver_id=str(profile.user_id))
    return incident


# --- 7.2 Chạy vòng ---------------------------------------------------------


@dataclass
class RouteDeviationResult:
    is_deviation: bool
    allowed_distance_km: Decimal
    billable_distance_km: Decimal
    excess_km: Decimal
    penalty_amount: Decimal


def evaluate_route_deviation(
    *,
    actual_distance_km: Decimal,
    optimal_distance_km: Decimal | None,
    per_km_rate: Decimal,
    factor: Decimal | None = None,
    penalty_multiplier: Decimal | None = None,
) -> RouteDeviationResult:
    """Vượt quá optimal × 1.5 -> không tính tiền phần vượt, phạt = chênh lệch × đơn giá km × 2."""
    factor = settings.ROUTE_DEVIATION_FACTOR if factor is None else factor
    penalty_multiplier = (
        settings.ROUTE_DEVIATION_PENALTY_MULTIPLIER
        if penalty_multiplier is None
        else penalty_multiplier
    )
    actual_distance_km = Decimal(actual_distance_km)

    if optimal_distance_km is None or Decimal(optimal_distance_km) <= 0:
        return RouteDeviationResult(
            is_deviation=False,
            allowed_distance_km=actual_distance_km,
            billable_distance_km=actual_distance_km,
            excess_km=Decimal("0"),
            penalty_amount=Decimal("0"),
        )

    allowed = (Decimal(optimal_distance_km) * factor).quantize(Decimal("0.01"))
    if actual_distance_km <= allowed:
        return RouteDeviationResult(
            is_deviation=False,
            allowed_distance_km=allowed,
            billable_distance_km=actual_distance_km,
            excess_km=Decimal("0"),
            penalty_amount=Decimal("0"),
        )

    excess = (actual_distance_km - allowed).quantize(Decimal("0.01"))
    penalty = vnd(excess * Decimal(per_km_rate) * penalty_multiplier)
    return RouteDeviationResult(
        is_deviation=True,
        allowed_distance_km=allowed,
        billable_distance_km=allowed,  # cap cước theo optimal × 1.5
        excess_km=excess,
        penalty_amount=penalty,
    )


async def check_route_deviation(
    db: AsyncSession,
    trip: Trip,
    profile: DriverProfile,
    *,
    actual_distance_km: Decimal,
    per_km_rate: Decimal,
) -> RouteDeviationResult:
    """Chạy trước khi chốt tiền ở bước complete (SPEC 5.2)."""
    result = evaluate_route_deviation(
        actual_distance_km=actual_distance_km,
        optimal_distance_km=trip.optimal_distance_km,
        per_km_rate=per_km_rate,
    )
    if not result.is_deviation:
        return result

    db.add(
        FraudIncident(
            trip_id=trip.id,
            driver_id=profile.user_id,
            fraud_type=FraudType.ROUTE_DEVIATION,
            detected_by=FraudDetectedBy.SYSTEM,
            severity=FraudSeverity.WARNING,
            penalty_amount=result.penalty_amount,
            details={
                "actual_distance_km": str(actual_distance_km),
                "optimal_distance_km": str(trip.optimal_distance_km),
                "allowed_distance_km": str(result.allowed_distance_km),
                "excess_km": str(result.excess_km),
            },
        )
    )
    profile.fraud_strikes += 1
    await escrow_service.penalize(
        db,
        profile,
        result.penalty_amount,
        note="Phạt chạy vòng",
        trip_id=trip.id,
    )
    await _lock_if_strikes_exceeded(db, profile)
    log_event(
        logger,
        "fraud_route_deviation",
        trip_id=str(trip.id),
        driver_id=str(profile.user_id),
        penalty=str(result.penalty_amount),
    )
    return result


# --- 7.3 Thanh toán ngoài app ---------------------------------------------


def online_hours_per_trip(online_seconds: float, completed_trips: int) -> float:
    """Tỷ lệ giờ online / chuyến hoàn thành. Không có chuyến nào -> trả giá trị lớn."""
    hours = online_seconds / 3600
    if completed_trips <= 0:
        return hours if hours > 0 else 0.0
    return hours / completed_trips


def is_anomalous_ratio(
    driver_ratio: float, system_avg_ratio: float, *, factor: float = 2.0
) -> bool:
    """Lệch bất thường khi tỷ lệ giờ online/đơn cao gấp `factor` lần trung bình hệ thống."""
    if system_avg_ratio <= 0:
        return False
    return driver_ratio >= system_avg_ratio * factor


async def scan_off_app_payment_signals(
    db: AsyncSession, *, since: datetime | None = None
) -> list[FraudReviewQueue]:
    """Cron hàng ngày: chỉ FLAG vào hàng đợi review, không tự động phạt (SPEC 7.3)."""
    since = since or datetime.now(timezone.utc) - timedelta(days=1)
    now = datetime.now(timezone.utc)

    sessions = (
        (
            await db.execute(
                select(DriverOnlineSession).where(DriverOnlineSession.started_at >= since)
            )
        )
        .scalars()
        .all()
    )
    online_seconds: dict[uuid.UUID, float] = {}
    for s in sessions:
        end = ensure_utc(s.ended_at) or now
        online_seconds[s.driver_id] = online_seconds.get(s.driver_id, 0.0) + max(
            (end - ensure_utc(s.started_at)).total_seconds(), 0.0
        )

    trip_rows = (
        await db.execute(
            select(Trip.driver_id, func.count(Trip.id))
            .where(
                # Phải tính cả chuyến đã được đánh giá, nếu không tài xế nào được khách
                # đánh giá nhiều sẽ bị đếm thiếu số chuyến và bị cờ nhầm là gian lận.
                Trip.status.in_(SETTLED_TRIP_STATUSES),
                Trip.completed_at >= since,
                Trip.driver_id.is_not(None),
            )
            .group_by(Trip.driver_id)
        )
    ).all()
    trips_count = {row[0]: row[1] for row in trip_rows}

    ratios = {
        driver_id: online_hours_per_trip(seconds, trips_count.get(driver_id, 0))
        for driver_id, seconds in online_seconds.items()
    }
    positive = [r for r in ratios.values() if r > 0]
    if not positive:
        return []
    system_avg = sum(positive) / len(positive)

    flagged: list[FraudReviewQueue] = []
    for driver_id, ratio in ratios.items():
        if not is_anomalous_ratio(ratio, system_avg):
            continue
        existing = (
            await db.execute(
                select(FraudReviewQueue.id).where(
                    FraudReviewQueue.driver_id == driver_id,
                    FraudReviewQueue.status == FraudReviewStatus.PENDING,
                )
            )
        ).first()
        if existing:
            continue
        item = FraudReviewQueue(
            driver_id=driver_id,
            reason="Tỷ lệ giờ online/đơn hoàn thành lệch bất thường",
            signal_score=round(ratio / system_avg, 3) if system_avg else 0.0,
            details={
                "online_hours": round(online_seconds[driver_id] / 3600, 2),
                "completed_trips": trips_count.get(driver_id, 0),
                "driver_ratio": round(ratio, 3),
                "system_avg_ratio": round(system_avg, 3),
            },
        )
        db.add(item)
        flagged.append(item)
    await db.commit()
    log_event(logger, "off_app_scan_completed", flagged=len(flagged))
    return flagged


async def confirm_off_app_payment(
    db: AsyncSession,
    *,
    profile: DriverProfile,
    user: User,
    trip: Trip | None,
    detected_by: FraudDetectedBy = FraudDetectedBy.REPORT,
) -> FraudIncident:
    """Xác nhận thủ công: cảnh cáo -> khoá khi đủ ngưỡng; chuyến liên quan mất quyền lợi bảo hiểm."""
    profile.fraud_strikes += 1
    locked = profile.fraud_strikes >= settings.FRAUD_STRIKE_LOCK_THRESHOLD
    if trip is not None:
        trip.insurance_voided = True

    incident = FraudIncident(
        trip_id=trip.id if trip else None,
        driver_id=profile.user_id,
        fraud_type=FraudType.OFF_APP_PAYMENT,
        detected_by=detected_by,
        severity=FraudSeverity.ACCOUNT_LOCKED if locked else FraudSeverity.WARNING,
        penalty_amount=Decimal("0"),
        details={"strikes": profile.fraud_strikes, "insurance_voided": trip is not None},
    )
    db.add(incident)
    if locked:
        user.status = UserStatus.BANNED
        profile.online_status = OnlineStatus.OFFLINE
        profile.active_qr_token = None
    await db.commit()
    log_event(
        logger,
        "fraud_off_app_confirmed",
        driver_id=str(profile.user_id),
        strikes=profile.fraud_strikes,
        locked=locked,
    )
    return incident


# --- 7.4 Tráo tài xế ------------------------------------------------------


@dataclass
class SelfieCheckOutcome:
    passed: bool
    match_score: float


def is_selfie_match(match_score: float, threshold: float | None = None) -> bool:
    return match_score >= (settings.SELFIE_MATCH_THRESHOLD if threshold is None else threshold)


async def verify_driver_selfie(
    db: AsyncSession, user: User, profile: DriverProfile, selfie_url: str
) -> SelfieCheckOutcome:
    from app.integrations.ekyc import get_ekyc_provider

    result = await get_ekyc_provider().match_face(
        profile.ekyc_selfie_reference_url or "", selfie_url
    )
    now = datetime.now(timezone.utc)
    profile.last_selfie_check_at = now

    if is_selfie_match(result.match_score):
        from app.domains.users.service import next_selfie_check_at

        profile.next_selfie_check_at = next_selfie_check_at(now)
        await db.commit()
        return SelfieCheckOutcome(passed=True, match_score=result.match_score)

    # Không khớp -> khoá vĩnh viễn ngay, giữ toàn bộ ký quỹ chờ admin review.
    user.status = UserStatus.BANNED
    profile.online_status = OnlineStatus.OFFLINE
    profile.active_qr_token = None
    profile.fraud_strikes += 1
    db.add(
        FraudIncident(
            driver_id=profile.user_id,
            fraud_type=FraudType.DRIVER_SWAP,
            detected_by=FraudDetectedBy.SYSTEM,
            severity=FraudSeverity.ACCOUNT_LOCKED,
            penalty_amount=Decimal("0"),
            details={
                "match_score": result.match_score,
                "threshold": settings.SELFIE_MATCH_THRESHOLD,
            },
        )
    )
    await escrow_service.lock_escrow_for_review(db, profile, reason="driver_swap")
    await db.commit()
    log_event(
        logger,
        "fraud_driver_swap",
        driver_id=str(profile.user_id),
        match_score=result.match_score,
    )
    return SelfieCheckOutcome(passed=False, match_score=result.match_score)


async def _lock_if_strikes_exceeded(db: AsyncSession, profile: DriverProfile) -> None:
    if profile.fraud_strikes < settings.FRAUD_STRIKE_LOCK_THRESHOLD:
        return
    user = await db.get(User, profile.user_id)
    if user is not None:
        user.status = UserStatus.SUSPENDED
        profile.online_status = OnlineStatus.OFFLINE
        profile.active_qr_token = None
    await db.flush()
