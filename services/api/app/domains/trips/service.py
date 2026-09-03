"""Trips service (SPEC 5) — vòng đời chuyến đi, chốt tiền, gọi fraud/escrow/payment.

Toàn bộ logic nghiệp vụ nằm ở đây; router chỉ điều phối request/response.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import (
    SETTLED_TRIP_STATUSES,
    OnlineStatus,
    PartnerType,
    TripActorType,
    TripEventType,
    TripStatus,
    UserRole,
)
from app.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.geo import haversine_km, haversine_m
from app.core.logging import log_event
from app.core.money import vnd
from app.core.timeutil import ensure_utc
from app.domains.escrow import service as escrow_service
from app.domains.fraud import service as fraud_service
from app.domains.notifications import service as notifications
from app.domains.partners import service as partners_service
from app.domains.partners.invoice import get_invoice_service
from app.domains.payments import service as payments_service
from app.domains.pricing import service as pricing_service
from app.domains.pricing.schemas import FareBreakdown
from app.domains.trips import events as trip_events
from app.domains.trips import repository as trips_repo
from app.domains.trips.models import Trip, TripRating
from app.domains.trips.schemas import TripCreate
from app.domains.trips.state_machine import assert_transition
from app.domains.users.models import DriverProfile, User
from app.integrations.maps import get_maps_provider
from app.websocket.events import ServerEvent

logger = logging.getLogger("goan.trips")

_TIMESTAMP_FIELD = {
    TripStatus.MATCHED: "matched_at",
    TripStatus.IN_PROGRESS: "started_at",
    TripStatus.COMPLETED: "completed_at",
    TripStatus.CANCELLED_BY_RIDER: "cancelled_at",
    TripStatus.CANCELLED_BY_DRIVER: "cancelled_at",
}


@dataclass
class CompleteResult:
    trip: Trip
    fare: FareBreakdown
    driver_actual_payout: Decimal
    escrow_deducted: Decimal
    route_deviation_detected: bool


async def _set_status(
    db: AsyncSession,
    trip: Trip,
    target: TripStatus,
    *,
    event: TripEventType,
    actor_type: TripActorType = TripActorType.SYSTEM,
    actor_id: uuid.UUID | None = None,
    **payload: object,
) -> Trip:
    """Đổi trạng thái và ghi dấu vết trong cùng một transaction.

    Gộp hai việc vào một hàm là có chủ ý: nếu tách ra thì sớm muộn cũng có chỗ đổi trạng
    thái mà quên ghi dấu vết, và dòng thời gian của chuyến sẽ khuyết đúng chỗ cần nhất.
    """
    previous = trip.status
    assert_transition(previous, target)
    trip.status = target
    field = _TIMESTAMP_FIELD.get(target)
    if field and getattr(trip, field) is None:
        setattr(trip, field, datetime.now(timezone.utc))
    await trip_events.record(
        db,
        trip.id,
        event,
        from_status=previous,
        to_status=target,
        actor_type=actor_type,
        actor_id=actor_id,
        **payload,
    )
    await db.flush()
    return trip


async def _notify_status(trip: Trip) -> None:
    targets = [trip.rider_id] + ([trip.driver_id] if trip.driver_id else [])
    await notifications.notify_users(
        targets, ServerEvent.TRIP_STATUS_CHANGED, trip_id=str(trip.id), status=trip.status.value
    )


# --- Tạo chuyến -----------------------------------------------------------


async def create_trip(
    db: AsyncSession, rider: User, payload: TripCreate
) -> tuple[Trip, FareBreakdown]:
    if payload.idempotency_key:
        existing = await trips_repo.get_trip_by_idempotency_key(db, payload.idempotency_key)
        if existing is not None:
            return existing, await _rebuild_estimate(db, existing)

    pickup_lat, pickup_lng = payload.pickup.lat, payload.pickup.lng
    pickup_address = payload.pickup_address
    restaurant_partner_id: uuid.UUID | None = None

    # Đặt xe tại bàn qua QR nhà hàng: pickup lấy theo toạ độ nhà hàng (SPEC 10.1).
    if payload.restaurant_partner_qr_token:
        partner = await partners_service.get_partner_by_qr(db, payload.restaurant_partner_qr_token)
        if partner.type is PartnerType.RESTAURANT:
            restaurant_partner_id = partner.id
            if partner.lat is not None and partner.lng is not None:
                pickup_lat, pickup_lng = partner.lat, partner.lng
                pickup_address = pickup_address or partner.address

    requested_at = datetime.now(timezone.utc)
    time_band = await pricing_service.resolve_time_band_db(db, requested_at)
    rule = await pricing_service.get_fare_rule(db, time_band)

    route = await get_maps_provider().get_route(
        pickup_lat, pickup_lng, payload.dropoff.lat, payload.dropoff.lng
    )
    breakdown = pricing_service.calculate_fare(
        distance_km=route.distance_km,
        duration_minutes=route.duration_minutes,
        time_band=time_band,
        rule=rule,
    )

    trip = Trip(
        rider_id=rider.id,
        status=TripStatus.REQUESTED,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        pickup_address=pickup_address,
        dropoff_lat=payload.dropoff.lat,
        dropoff_lng=payload.dropoff.lng,
        dropoff_address=payload.dropoff_address,
        time_band=time_band,
        estimated_fare=breakdown.final_fare,
        distance_km=route.distance_km,
        duration_minutes=route.duration_minutes,
        optimal_distance_km=route.distance_km,
        route_polyline=route.polyline,
        requested_at=requested_at,
        restaurant_partner_id=restaurant_partner_id,
        idempotency_key=payload.idempotency_key,
    )
    db.add(trip)
    await db.flush()
    await trip_events.record(
        db,
        trip.id,
        TripEventType.CREATED,
        to_status=TripStatus.REQUESTED,
        actor_type=TripActorType.RIDER,
        actor_id=rider.id,
        estimated_fare=str(breakdown.final_fare),
        pickup_address=pickup_address,
        dropoff_address=payload.dropoff_address,
    )
    await db.commit()
    await db.refresh(trip)
    log_event(
        logger,
        "trip_created",
        trip_id=str(trip.id),
        rider_id=str(rider.id),
        time_band=time_band.value,
        estimated_fare=str(breakdown.final_fare),
    )
    return trip, breakdown


async def _rebuild_estimate(db: AsyncSession, trip: Trip) -> FareBreakdown:
    rule = await pricing_service.get_fare_rule(db, trip.time_band)
    return pricing_service.calculate_fare(
        distance_km=trip.distance_km or Decimal("0"),
        duration_minutes=trip.duration_minutes or 0,
        time_band=trip.time_band,
        driver_to_pickup_distance_km=trip.driver_to_pickup_distance_km,
        rule=rule,
    )


async def get_trip_for_user(db: AsyncSession, trip_id: uuid.UUID, user: User) -> Trip:
    trip = await trips_repo.get_trip(db, trip_id)
    if trip is None:
        raise NotFoundError("Không tìm thấy chuyến")
    if user.role is not UserRole.ADMIN and user.id not in {trip.rider_id, trip.driver_id}:
        raise PermissionDeniedError("Không có quyền với chuyến này")
    return trip


# --- 7.1 Quét QR -> in_progress -----------------------------------------


async def verify_qr(db: AsyncSession, trip: Trip, rider: User, qr_token: str) -> Trip:
    """Rider quét QR tài xế. Không qua bước này thì chuyến KHÔNG thể vào in_progress."""
    if trip.rider_id != rider.id:
        raise PermissionDeniedError("Chỉ khách của chuyến mới được quét QR")
    if trip.driver_id is None:
        raise ConflictError("Chuyến chưa có tài xế")

    profile = await _get_driver_profile(db, trip.driver_id)
    await fraud_service.check_qr_verified(db, trip, profile, qr_token)

    await _set_status(
        db,
        trip,
        TripStatus.QR_VERIFIED,
        event=TripEventType.QR_VERIFIED,
        actor_type=TripActorType.RIDER,
        actor_id=rider.id,
    )
    trip.qr_verified_at = datetime.now(timezone.utc)
    # qr_verified -> in_progress là tự động ngay sau khi quét thành công (SPEC 5.1).
    await _set_status(
        db,
        trip,
        TripStatus.IN_PROGRESS,
        event=TripEventType.QR_VERIFIED,
        actor_type=TripActorType.RIDER,
        actor_id=rider.id,
    )
    profile.online_status = OnlineStatus.ON_TRIP
    await db.commit()
    await _notify_status(trip)
    log_event(logger, "trip_qr_verified", trip_id=str(trip.id), driver_id=str(trip.driver_id))
    return trip


async def record_gps_ping(
    db: AsyncSession, trip: Trip, driver: User, lat: float, lng: float, recorded_at: datetime | None
) -> None:
    if trip.driver_id != driver.id:
        raise PermissionDeniedError("Chuyến không thuộc về tài xế này")
    if trip.status not in {TripStatus.DRIVER_ARRIVING, TripStatus.IN_PROGRESS}:
        raise ConflictError("Chỉ ghi GPS khi đang đón khách hoặc đang chạy")

    await trips_repo.add_gps_log(db, trip.id, lat, lng, recorded_at or datetime.now(timezone.utc))
    await db.commit()
    await notifications.notify_user(
        trip.rider_id, ServerEvent.DRIVER_LOCATION, trip_id=str(trip.id), lat=lat, lng=lng
    )


# --- Hoàn tất chuyến ------------------------------------------------------


async def complete_trip(
    db: AsyncSession,
    trip: Trip,
    driver: User,
    *,
    lat: float | None = None,
    lng: float | None = None,
    idempotency_key: str | None = None,
) -> CompleteResult:
    """Chốt chuyến theo đúng thứ tự SPEC 5.2, toàn bộ trong một transaction."""
    if trip.driver_id != driver.id:
        raise PermissionDeniedError("Chuyến không thuộc về tài xế này")

    # Idempotent: mobile network chập chờn dễ gửi trùng request (SPEC 13).
    # Tính cả `rated`: khách có thể đánh giá rất nhanh, và request complete gửi lại do mất
    # sóng vẫn phải trả về kết quả cũ thay vì báo lỗi.
    if trip.status in SETTLED_TRIP_STATUSES:
        return CompleteResult(
            trip=trip,
            fare=await _rebuild_final_fare(db, trip),
            driver_actual_payout=trip.driver_payout or Decimal("0"),
            escrow_deducted=Decimal("0"),
            route_deviation_detected=False,
        )

    profile = await _get_driver_profile(db, driver.id)

    # Chưa quét QR mà đòi kết thúc chuyến -> đơn ma (SPEC 7.1, 7.5).
    if trip.status is not TripStatus.IN_PROGRESS or trip.qr_verified_at is None:
        if trip.status in {TripStatus.MATCHED, TripStatus.DRIVER_ARRIVING}:
            await fraud_service.report_ghost_trip(
                db, trip, profile, driver, reason="Kết thúc chuyến khi chưa quét QR"
            )
            await db.commit()
        raise ConflictError("Chuyến chưa ở trạng thái đang chạy")

    if (
        lat is not None
        and lng is not None
        and trip.dropoff_lat is not None
        and trip.dropoff_lng is not None
    ):
        distance_to_dropoff = haversine_m(lat, lng, trip.dropoff_lat, trip.dropoff_lng)
        if distance_to_dropoff > settings.TRIP_COMPLETE_RADIUS_M:
            raise ConflictError(
                f"Tài xế đang cách điểm đến {int(distance_to_dropoff)}m, cần ở trong bán kính "
                f"{settings.TRIP_COMPLETE_RADIUS_M}m để kết thúc chuyến"
            )

    now = datetime.now(timezone.utc)
    started_at = ensure_utc(trip.started_at) or now
    duration_minutes = max(int((now - started_at).total_seconds() // 60), 1)

    points = await trips_repo.list_gps_logs(db, trip.id)
    actual_distance_km = trips_repo.total_gps_distance_km(points)
    if actual_distance_km <= 0:
        actual_distance_km = trip.optimal_distance_km or Decimal("0")

    rule = await pricing_service.get_fare_rule(db, trip.time_band)

    # (2) Chống gian lận chạy vòng TRƯỚC khi chốt tiền.
    deviation = await fraud_service.check_route_deviation(
        db,
        trip,
        profile,
        actual_distance_km=actual_distance_km,
        per_km_rate=rule.per_km,
    )

    # (1) Tính cước theo số liệu thực tế (đã cap nếu chạy vòng).
    fare = pricing_service.calculate_fare(
        distance_km=deviation.billable_distance_km,
        duration_minutes=duration_minutes,
        time_band=trip.time_band,
        driver_to_pickup_distance_km=trip.driver_to_pickup_distance_km,
        rule=rule,
    )

    insurance_rate = await partners_service.get_insurance_fee_rate(db)
    insurance_fee = (
        vnd(fare.final_fare * insurance_rate) if insurance_rate is not None else fare.insurance_fee
    )

    # (3) Ghi nhận doanh thu vào trip.
    trip.distance_km = actual_distance_km
    trip.duration_minutes = duration_minutes
    trip.final_fare = fare.final_fare
    trip.pickup_surcharge = fare.pickup_surcharge
    trip.driver_payout = fare.driver_payout
    trip.platform_commission = fare.platform_commission
    trip.insurance_fee = insurance_fee

    # (4) Trích ký quỹ 15% từ driver_payout nếu đang tích luỹ.
    actual_payout = await escrow_service.accrue(db, profile, fare.driver_payout, trip_id=trip.id)
    escrow_deducted = vnd(fare.driver_payout - actual_payout)

    # (5) Thu tiền rider + cộng ví tài xế (pending).
    await payments_service.charge_trip(
        db, trip, amount=fare.final_fare, idempotency_key=idempotency_key
    )
    await payments_service.credit_driver_wallet(db, driver.id, actual_payout, trip_id=trip.id)

    await partners_service.record_trip_commission(db, trip)

    profile.total_trips += 1
    profile.online_status = OnlineStatus.ONLINE
    await _set_status(
        db,
        trip,
        TripStatus.COMPLETED,
        event=TripEventType.COMPLETED,
        actor_type=TripActorType.DRIVER,
        actor_id=driver.id,
        final_fare=str(fare.final_fare),
        driver_payout=str(actual_payout),
        escrow_deducted=str(escrow_deducted),
        distance_km=str(actual_distance_km),
        route_deviation=deviation.is_deviation,
    )
    await db.commit()

    # Hoá đơn VAT cho chuyến từ khách sạn đối tác (SPEC 10.2).
    if trip.restaurant_partner_id is not None:
        partner = await partners_service.get_partner(db, trip.restaurant_partner_id)
        if partner.requires_vat_invoice:
            await get_invoice_service().issue_vat_invoice(trip.id)

    # (6) Emit WS event cho cả rider và driver.
    await notifications.notify_users(
        [trip.rider_id, driver.id],
        ServerEvent.TRIP_COMPLETED,
        trip_id=str(trip.id),
        final_fare=str(fare.final_fare),
        driver_payout=str(actual_payout),
    )
    log_event(
        logger,
        "trip_completed",
        trip_id=str(trip.id),
        final_fare=str(fare.final_fare),
        driver_payout=str(actual_payout),
        escrow_deducted=str(escrow_deducted),
        route_deviation=deviation.is_deviation,
    )
    return CompleteResult(
        trip=trip,
        fare=fare.model_copy(update={"insurance_fee": insurance_fee}),
        driver_actual_payout=actual_payout,
        escrow_deducted=escrow_deducted,
        route_deviation_detected=deviation.is_deviation,
    )


async def _rebuild_final_fare(db: AsyncSession, trip: Trip) -> FareBreakdown:
    rule = await pricing_service.get_fare_rule(db, trip.time_band)
    return pricing_service.calculate_fare(
        distance_km=trip.distance_km or Decimal("0"),
        duration_minutes=trip.duration_minutes or 0,
        time_band=trip.time_band,
        driver_to_pickup_distance_km=trip.driver_to_pickup_distance_km,
        rule=rule,
    )


# --- Huỷ chuyến -----------------------------------------------------------


async def cancel_trip(
    db: AsyncSession,
    trip: Trip,
    user: User,
    reason: str | None,
    *,
    on_behalf_of_ops: bool = False,
) -> Trip:
    """Huỷ chuyến. Khách huỷ muộn thì chịu phí huỷ, và phí đó ĐƯỢC TRẢ CHO TÀI XẾ.

    `on_behalf_of_ops`: CSKH huỷ hộ khi khách gọi tổng đài hoặc tài xế mất liên lạc. Bắt
    buộc có lý do và ghi rõ người thao tác vào dòng thời gian của chuyến.
    """
    if on_behalf_of_ops:
        if not reason:
            raise AppError("Huỷ hộ bắt buộc phải ghi lý do")
        target = TripStatus.CANCELLED_BY_RIDER
        actor_type = TripActorType.ADMIN
    elif user.id == trip.rider_id:
        target = TripStatus.CANCELLED_BY_RIDER
        actor_type = TripActorType.RIDER
    elif trip.driver_id is not None and user.id == trip.driver_id:
        if not reason:
            raise AppError("Tài xế huỷ chuyến bắt buộc phải có lý do")
        target = TripStatus.CANCELLED_BY_DRIVER
        actor_type = TripActorType.DRIVER
    else:
        raise PermissionDeniedError("Không có quyền huỷ chuyến này")

    # Khách huỷ muộn (quá X phút sau khi ghép) thì chịu phí huỷ. CSKH huỷ hộ thì miễn phí —
    # nếu tính phí thì mọi cuộc gọi tổng đài đều thành một khoản tranh chấp.
    charge_fee = (
        target is TripStatus.CANCELLED_BY_RIDER
        and not on_behalf_of_ops
        and trip.matched_at is not None
        and datetime.now(timezone.utc) - ensure_utc(trip.matched_at)
        > timedelta(minutes=settings.CANCELLATION_GRACE_MINUTES)
    )
    if charge_fee:
        trip.cancellation_fee = vnd(settings.CANCELLATION_FEE)

    await _set_status(
        db,
        trip,
        target,
        event=TripEventType.CANCELLED,
        actor_type=actor_type,
        actor_id=user.id,
        reason=reason or "",
        cancellation_fee=str(trip.cancellation_fee),
        on_behalf_of_ops=on_behalf_of_ops,
    )
    trip.cancellation_reason = reason

    if trip.driver_id is not None:
        profile = await _get_driver_profile(db, trip.driver_id)
        if profile.online_status is OnlineStatus.ON_TRIP:
            profile.online_status = OnlineStatus.ONLINE

        # Phí huỷ phải THỰC SỰ tới tay tài xế. Trước đây con số chỉ được ghi vào bảng trips
        # và không có bút toán nào — tài xế chạy tới điểm đón rồi bị huỷ là mất công trắng.
        if charge_fee and trip.cancellation_fee > 0:
            await payments_service.charge_trip(
                db, trip, amount=trip.cancellation_fee, idempotency_key=f"cancel-{trip.id}"
            )
            await payments_service.credit_driver_wallet(
                db, trip.driver_id, trip.cancellation_fee, trip_id=trip.id
            )

    await db.commit()
    await _notify_status(trip)
    log_event(
        logger,
        "trip_cancelled",
        trip_id=str(trip.id),
        by=target.value,
        reason=reason or "",
        cancellation_fee=str(trip.cancellation_fee),
    )
    return trip


# --- Tài xế báo đã tới điểm đón ------------------------------------------


async def mark_driver_arrived(
    db: AsyncSession, trip: Trip, driver: User, lat: float | None, lng: float | None
) -> Trip:
    """Mốc "tài xế đã tới điểm đón".

    Trước đây không có mốc này: `driver_arriving` được đặt ngay lúc tài xế bấm nhận chuyến,
    nên app khách hiện "tài xế đã đến" khi tài xế còn cách vài km. Đây là trạng thái phụ
    (một mốc thời gian), không phải trạng thái mới trong state machine — chuyến vẫn ở
    `driver_arriving` cho tới khi khách quét QR.
    """
    if trip.driver_id != driver.id:
        raise PermissionDeniedError("Chuyến không thuộc về tài xế này")
    if trip.status is not TripStatus.DRIVER_ARRIVING:
        raise ConflictError("Chỉ báo đã tới khi đang trên đường đón khách")
    if trip.driver_arrived_at is not None:
        return trip  # idempotent: bấm hai lần không đổi gì

    distance_m: float | None = None
    if lat is not None and lng is not None:
        distance_m = haversine_m(lat, lng, trip.pickup_lat, trip.pickup_lng)

    trip.driver_arrived_at = datetime.now(timezone.utc)
    await trip_events.record(
        db,
        trip.id,
        TripEventType.DRIVER_ARRIVED,
        from_status=trip.status,
        to_status=trip.status,
        actor_type=TripActorType.DRIVER,
        actor_id=driver.id,
        distance_to_pickup_m=int(distance_m) if distance_m is not None else None,
    )
    await db.commit()
    await notifications.notify_user(
        trip.rider_id,
        ServerEvent.TRIP_STATUS_CHANGED,
        trip_id=str(trip.id),
        status=trip.status.value,
        driver_arrived=True,
    )
    log_event(
        logger,
        "trip_driver_arrived",
        trip_id=str(trip.id),
        distance_to_pickup_m=str(int(distance_m)) if distance_m is not None else "",
    )
    return trip


# --- Đánh giá sau chuyến --------------------------------------------------


async def rate_trip(
    db: AsyncSession, trip: Trip, rider: User, stars: int, comment: str | None
) -> tuple[TripRating, DriverProfile]:
    """Khách đánh giá tài xế — bước cuối của vòng đời chuyến (deck mục 3.3: `rated`)."""
    if trip.rider_id != rider.id:
        raise PermissionDeniedError("Chỉ khách của chuyến mới được đánh giá")
    if trip.status is not TripStatus.COMPLETED:
        raise ConflictError("Chỉ đánh giá được chuyến đã hoàn thành")
    if trip.driver_id is None:
        raise ConflictError("Chuyến không có tài xế để đánh giá")

    existing = await trips_repo.get_rating(db, trip.id)
    if existing is not None:
        raise ConflictError("Chuyến này đã được đánh giá rồi")

    rating = TripRating(
        trip_id=trip.id,
        rider_id=rider.id,
        driver_id=trip.driver_id,
        stars=stars,
        comment=comment,
    )
    db.add(rating)
    await db.flush()

    profile = await _get_driver_profile(db, trip.driver_id)
    # Tính lại trung bình từ toàn bộ đánh giá thay vì cộng dồn tăng dần: cộng dồn thì mọi
    # lần sửa/xoá đánh giá về sau đều làm lệch vĩnh viễn, và không đối chiếu lại được.
    avg, total = await trips_repo.driver_rating_stats(db, trip.driver_id)
    profile.rating_avg = avg

    trip.rated_at = datetime.now(timezone.utc)
    await _set_status(
        db,
        trip,
        TripStatus.RATED,
        event=TripEventType.RATED,
        actor_type=TripActorType.RIDER,
        actor_id=rider.id,
        stars=stars,
    )
    await db.commit()
    log_event(
        logger,
        "trip_rated",
        trip_id=str(trip.id),
        stars=str(stars),
        driver_rating_avg=str(avg),
        driver_total_ratings=str(total),
    )
    return rating, profile


async def _get_driver_profile(db: AsyncSession, driver_user_id: uuid.UUID) -> DriverProfile:
    from app.domains.users import repository as users_repo

    profile = await users_repo.get_driver_profile_by_user(db, driver_user_id)
    if profile is None:
        raise NotFoundError("Không tìm thấy hồ sơ tài xế")
    return profile


def distance_driver_to_pickup(driver_lat: float, driver_lng: float, trip: Trip) -> Decimal:
    return haversine_km(driver_lat, driver_lng, trip.pickup_lat, trip.pickup_lng)
