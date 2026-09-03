"""Users/driver service: eKYC, trạng thái online, vị trí, QR động."""

import logging
import random
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import OnlineStatus
from app.core.exceptions import ConflictError
from app.core.logging import log_event
from app.core.security import encrypt_national_id, generate_qr_token, mask_national_id
from app.domains.fraud.models import DriverOnlineSession
from app.domains.users.models import DriverProfile, User
from app.integrations.ekyc import get_ekyc_provider
from app.redis_client import DRIVER_GEO_KEY

logger = logging.getLogger("goan.users")


def next_selfie_check_at(now: datetime) -> datetime:
    """Selfie ngẫu nhiên 30-90 phút/lần khi online (SPEC 7.4)."""
    minutes = random.randint(
        settings.SELFIE_CHECK_MIN_INTERVAL_MINUTES, settings.SELFIE_CHECK_MAX_INTERVAL_MINUTES
    )
    return now + timedelta(minutes=minutes)


async def submit_ekyc(
    db: AsyncSession,
    user: User,
    profile: DriverProfile,
    national_id: str,
    selfie_reference_url: str,
) -> User:
    result = await get_ekyc_provider().verify_national_id(national_id, user.full_name)
    user.national_id_number = encrypt_national_id(national_id)  # mã hoá at-rest (SPEC 13)
    user.national_id_verified = result.verified
    profile.ekyc_selfie_reference_url = selfie_reference_url
    await db.commit()
    log_event(logger, "ekyc_submitted", user_id=str(user.id), verified=result.verified)
    return user


async def go_online(
    db: AsyncSession, redis: Redis, profile: DriverProfile, lat: float, lng: float
) -> str:
    if profile.online_status is OnlineStatus.ON_TRIP:
        raise ConflictError("Tài xế đang trong chuyến")
    if not profile.ekyc_selfie_reference_url:
        raise ConflictError("Cần hoàn tất eKYC trước khi nhận chuyến")

    now = datetime.now(timezone.utc)
    profile.active_qr_token = generate_qr_token()  # QR đổi mỗi phiên online (SPEC 7.1)
    profile.online_status = OnlineStatus.ONLINE
    profile.current_lat, profile.current_lng = lat, lng
    profile.next_selfie_check_at = next_selfie_check_at(now)
    db.add(DriverOnlineSession(driver_id=profile.user_id, started_at=now))
    await db.commit()

    await redis.geoadd(DRIVER_GEO_KEY, (lng, lat, str(profile.user_id)))
    log_event(logger, "driver_online", driver_id=str(profile.user_id))
    return profile.active_qr_token


async def go_offline(db: AsyncSession, redis: Redis, profile: DriverProfile) -> None:
    if profile.online_status is OnlineStatus.ON_TRIP:
        raise ConflictError("Không thể offline khi đang có chuyến")
    profile.online_status = OnlineStatus.OFFLINE
    profile.active_qr_token = None
    stmt = (
        select(DriverOnlineSession)
        .where(
            DriverOnlineSession.driver_id == profile.user_id,
            DriverOnlineSession.ended_at.is_(None),
        )
        .order_by(DriverOnlineSession.started_at.desc())
        .limit(1)
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is not None:
        session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await redis.zrem(DRIVER_GEO_KEY, str(profile.user_id))
    log_event(logger, "driver_offline", driver_id=str(profile.user_id))


async def update_location(
    db: AsyncSession, redis: Redis, profile: DriverProfile, lat: float, lng: float
) -> None:
    profile.current_lat, profile.current_lng = lat, lng
    await db.commit()
    if profile.online_status is not OnlineStatus.OFFLINE:
        await redis.geoadd(DRIVER_GEO_KEY, (lng, lat, str(profile.user_id)))


def masked_national_id(user: User) -> str | None:
    """Chỉ dùng ở tầng hiển thị — không giải mã ra log."""
    if not user.national_id_number:
        return None
    from app.core.security import decrypt_national_id

    try:
        return mask_national_id(decrypt_national_id(user.national_id_number))
    except Exception:  # dữ liệu cũ chưa mã hoá
        return mask_national_id(user.national_id_number)
