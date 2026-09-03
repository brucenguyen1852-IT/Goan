"""Matching service (SPEC 6) — stateless per-worker, mọi state chia sẻ nằm ở Redis.

- Vị trí tài xế: Redis GEO `driver_locations` (mọi worker query được).
- Chống race 2 tài xế cùng accept: `SETNX trip:{id}:lock`.
- Fan-out offer tới N tài xế gần nhất, ai accept trước thắng.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import OnlineStatus, TripStatus, UserStatus
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.geo import haversine_km
from app.core.logging import log_event
from app.core.money import vnd
from app.domains.notifications import service as notifications
from app.domains.partners import service as partners_service
from app.domains.pricing import service as pricing_service
from app.domains.trips.models import Trip
from app.domains.trips.state_machine import assert_transition
from app.domains.users import repository as users_repo
from app.domains.users.models import DriverProfile
from app.redis_client import DRIVER_GEO_KEY, TRIP_LOCK_KEY, TRIP_OFFER_KEY
from app.websocket.events import ServerEvent

logger = logging.getLogger("goan.matching")


@dataclass
class NearbyDriver:
    driver_id: uuid.UUID
    distance_km: Decimal


async def find_nearby_drivers(
    db: AsyncSession, redis: Redis, *, lat: float, lng: float, limit: int | None = None
) -> list[NearbyDriver]:
    """Nới dần bán kính 5km -> 8km -> 12km cho tới khi có ứng viên hợp lệ."""
    limit = limit or settings.MATCHING_OFFER_FANOUT
    for radius in settings.MATCHING_RADIUS_STEPS_KM:
        raw = await redis.geosearch(
            DRIVER_GEO_KEY,
            longitude=lng,
            latitude=lat,
            radius=radius,
            unit="km",
            sort="ASC",
            count=limit * 3,
            withdist=True,
        )
        if not raw:
            continue
        candidates = {uuid.UUID(item[0]): Decimal(str(round(item[1], 2))) for item in raw}
        profiles = await users_repo.get_driver_profiles_by_user_ids(db, list(candidates))
        eligible = [
            NearbyDriver(driver_id=p.user_id, distance_km=candidates[p.user_id])
            for p in profiles
            if _is_eligible(p)
        ]
        if eligible:
            eligible.sort(key=lambda d: d.distance_km)
            return eligible[:limit]
    return []


def _is_eligible(profile: DriverProfile) -> bool:
    """Chỉ tài xế đang online (không đang chuyến khác) và chưa quá ngưỡng cảnh cáo."""
    if profile.online_status is not OnlineStatus.ONLINE:
        return False
    if profile.fraud_strikes >= settings.FRAUD_STRIKE_LOCK_THRESHOLD:
        return False
    return profile.user is None or profile.user.status is UserStatus.ACTIVE


async def start_matching(db: AsyncSession, redis: Redis, trip: Trip) -> list[NearbyDriver]:
    """requested -> matching, rồi broadcast offer cho N tài xế gần nhất."""
    if trip.status is TripStatus.REQUESTED:
        assert_transition(trip.status, TripStatus.MATCHING)
        trip.status = TripStatus.MATCHING
        await db.commit()

    drivers = await find_nearby_drivers(db, redis, lat=trip.pickup_lat, lng=trip.pickup_lng)
    if not drivers:
        await mark_no_driver_found(db, trip)
        return []

    key = TRIP_OFFER_KEY.format(trip_id=trip.id)
    await redis.delete(key)
    await redis.sadd(key, *[str(d.driver_id) for d in drivers])
    await redis.expire(key, settings.MATCHING_TIMEOUT_SECONDS)

    await notifications.notify_users(
        [d.driver_id for d in drivers],
        ServerEvent.TRIP_OFFER,
        trip_id=str(trip.id),
        pickup={"lat": trip.pickup_lat, "lng": trip.pickup_lng, "address": trip.pickup_address},
        dropoff={"lat": trip.dropoff_lat, "lng": trip.dropoff_lng, "address": trip.dropoff_address},
        estimated_fare=str(trip.estimated_fare or 0),
        expires_in_sec=settings.MATCHING_OFFER_TTL_SECONDS,
    )
    log_event(logger, "trip_offers_sent", trip_id=str(trip.id), drivers=len(drivers))
    return drivers


async def accept_offer(
    db: AsyncSession, redis: Redis, trip: Trip, driver_user_id: uuid.UUID
) -> Trip:
    """Ai accept trước thắng — dùng SETNX làm khoá phân tán."""
    if trip.status is not TripStatus.MATCHING:
        raise ConflictError("Chuyến không còn ở trạng thái đang tìm tài xế")

    offer_key = TRIP_OFFER_KEY.format(trip_id=trip.id)
    if await redis.exists(offer_key) and not await redis.sismember(offer_key, str(driver_user_id)):
        raise PermissionDeniedError("Tài xế không nằm trong danh sách được mời chuyến này")

    lock_key = TRIP_LOCK_KEY.format(trip_id=trip.id)
    acquired = await redis.set(
        lock_key, str(driver_user_id), nx=True, ex=settings.MATCHING_TIMEOUT_SECONDS
    )
    if not acquired:
        raise ConflictError("Chuyến đã được tài xế khác nhận")

    profile = await users_repo.get_driver_profile_by_user(db, driver_user_id)
    if profile is None:
        await redis.delete(lock_key)
        raise NotFoundError("Không tìm thấy hồ sơ tài xế")
    if not _is_eligible(profile):
        await redis.delete(lock_key)
        raise PermissionDeniedError("Tài xế không đủ điều kiện nhận chuyến")

    assert_transition(trip.status, TripStatus.MATCHED)
    trip.driver_id = driver_user_id
    trip.status = TripStatus.MATCHED
    trip.matched_at = datetime.now(timezone.utc)

    if profile.current_lat is not None and profile.current_lng is not None:
        trip.driver_to_pickup_distance_km = haversine_km(
            profile.current_lat, profile.current_lng, trip.pickup_lat, trip.pickup_lng
        )
        trip.pickup_surcharge = pricing_service.calculate_pickup_surcharge(
            trip.driver_to_pickup_distance_km
        )
        # Cập nhật lại ước tính đã gồm phụ thu đón xa để rider thấy trước khi lên xe.
        rule = await pricing_service.get_fare_rule(db, trip.time_band)
        estimate = pricing_service.calculate_fare(
            distance_km=trip.distance_km or Decimal("0"),
            duration_minutes=trip.duration_minutes or 0,
            time_band=trip.time_band,
            driver_to_pickup_distance_km=trip.driver_to_pickup_distance_km,
            rule=rule,
        )
        trip.estimated_fare = estimate.final_fare

    # Trợ cấp vùng mới: hạch toán riêng, KHÔNG trừ payout/commission (SPEC 6.4).
    zone = await partners_service.find_new_zone_for_pickup(db, trip.pickup_lat, trip.pickup_lng)
    if zone is not None:
        subsidy = vnd(settings.NEW_ZONE_SUBSIDY_AMOUNT)
        trip.pickup_surcharge_subsidized = subsidy
        await partners_service.record_marketing_subsidy(db, trip, zone, subsidy)

    profile.online_status = OnlineStatus.ON_TRIP
    await db.flush()

    # matched -> driver_arriving là bước tự động (SPEC 5.1).
    assert_transition(trip.status, TripStatus.DRIVER_ARRIVING)
    trip.status = TripStatus.DRIVER_ARRIVING
    await db.commit()
    await redis.delete(offer_key)

    eta_minutes = _eta_minutes(trip.driver_to_pickup_distance_km)
    await notifications.notify_user(
        trip.rider_id,
        ServerEvent.TRIP_MATCHED,
        trip_id=str(trip.id),
        driver={
            "id": str(profile.user_id),
            "name": profile.user.full_name if profile.user else None,
            "phone": profile.user.phone if profile.user else None,
            "rating": str(profile.rating_avg),
            "avatar": profile.user.avatar_url if profile.user else None,
        },
        eta_minutes=eta_minutes,
    )
    log_event(logger, "trip_matched", trip_id=str(trip.id), driver_id=str(driver_user_id))
    return trip


def _eta_minutes(distance_km: Decimal | None) -> int:
    if not distance_km:
        return 5
    return max(int(Decimal(distance_km) / Decimal("25") * Decimal("60")), 1)


async def mark_no_driver_found(db: AsyncSession, trip: Trip) -> Trip:
    """Hết 90s không ai nhận -> no_driver_found (có thể retry hoặc trợ cấp)."""
    if trip.status is TripStatus.MATCHING:
        assert_transition(trip.status, TripStatus.NO_DRIVER_FOUND)
        trip.status = TripStatus.NO_DRIVER_FOUND
        await db.commit()
        await notifications.notify_user(
            trip.rider_id,
            ServerEvent.TRIP_STATUS_CHANGED,
            trip_id=str(trip.id),
            status=trip.status.value,
        )
        log_event(logger, "trip_no_driver_found", trip_id=str(trip.id))
    return trip


async def expire_stale_matching_trips(db: AsyncSession) -> int:
    """Celery beat: dọn các chuyến quá hạn timeout mà chưa ai nhận."""
    deadline = datetime.now(timezone.utc) - timedelta(seconds=settings.MATCHING_TIMEOUT_SECONDS)
    stmt = select(Trip).where(Trip.status == TripStatus.MATCHING, Trip.requested_at <= deadline)
    trips = list((await db.execute(stmt)).scalars().all())
    for trip in trips:
        await mark_no_driver_found(db, trip)
    return len(trips)
