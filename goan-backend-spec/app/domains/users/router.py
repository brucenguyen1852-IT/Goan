from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_driver, get_current_user, get_driver_profile, get_redis
from app.domains.fraud import service as fraud_service
from app.domains.users import service as users_service
from app.domains.users.models import DriverProfile, User
from app.domains.users.schemas import (
    DriverProfileOut,
    EkycResult,
    EkycSubmit,
    GoOnlineResponse,
    LocationUpdate,
    SelfieCheckResult,
    SelfieCheckSubmit,
    UserOut,
)

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=user.id,
        phone=user.phone,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        national_id_verified=user.national_id_verified,
        national_id_masked=users_service.masked_national_id(user),
        avatar_url=user.avatar_url,
    )


@router.get("/drivers/me", response_model=DriverProfileOut)
async def my_driver_profile(
    profile: DriverProfile = Depends(get_driver_profile),
) -> DriverProfileOut:
    return DriverProfileOut.model_validate(profile, from_attributes=True)


@router.post("/drivers/me/ekyc", response_model=EkycResult)
async def submit_ekyc(
    payload: EkycSubmit,
    user: User = Depends(get_current_driver),
    profile: DriverProfile = Depends(get_driver_profile),
    db: AsyncSession = Depends(get_db),
) -> EkycResult:
    user = await users_service.submit_ekyc(
        db, user, profile, payload.national_id_number, payload.selfie_reference_url
    )
    return EkycResult(
        national_id_verified=user.national_id_verified,
        national_id_masked=users_service.masked_national_id(user),
    )


@router.post("/drivers/me/online", response_model=GoOnlineResponse)
async def go_online(
    payload: LocationUpdate,
    profile: DriverProfile = Depends(get_driver_profile),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> GoOnlineResponse:
    """Bật nhận chuyến: sinh QR động mới cho phiên online này (SPEC 7.1)."""
    qr_token = await users_service.go_online(db, redis, profile, payload.lat, payload.lng)
    return GoOnlineResponse(online_status=profile.online_status, qr_token=qr_token)


@router.post("/drivers/me/offline", status_code=status.HTTP_204_NO_CONTENT)
async def go_offline(
    profile: DriverProfile = Depends(get_driver_profile),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    await users_service.go_offline(db, redis, profile)


@router.post("/drivers/me/location", status_code=status.HTTP_204_NO_CONTENT)
async def update_location(
    payload: LocationUpdate,
    profile: DriverProfile = Depends(get_driver_profile),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    await users_service.update_location(db, redis, profile, payload.lat, payload.lng)


@router.post("/drivers/me/selfie-check", response_model=SelfieCheckResult)
async def selfie_check(
    payload: SelfieCheckSubmit,
    user: User = Depends(get_current_driver),
    profile: DriverProfile = Depends(get_driver_profile),
    db: AsyncSession = Depends(get_db),
) -> SelfieCheckResult:
    """Selfie ngẫu nhiên chống tráo tài xế; không khớp -> khoá tài khoản ngay (SPEC 7.4)."""
    outcome = await fraud_service.verify_driver_selfie(db, user, profile, payload.selfie_url)
    return SelfieCheckResult(
        passed=outcome.passed, match_score=outcome.match_score, account_status=user.status
    )
