from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_redis
from app.domains.auth import service as auth_service
from app.domains.auth.schemas import (
    OtpRequest,
    OtpRequestResponse,
    OtpVerify,
    RefreshRequest,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp", response_model=OtpRequestResponse)
async def request_otp(payload: OtpRequest, redis: Redis = Depends(get_redis)) -> OtpRequestResponse:
    otp = await auth_service.request_otp(redis, payload.phone)
    return OtpRequestResponse(
        phone=payload.phone,
        expires_in_sec=settings.OTP_TTL_SECONDS,
        debug_otp=otp if settings.DEBUG else None,
    )


@router.post("/verify-otp", response_model=TokenPair)
async def verify_otp(
    payload: OtpVerify,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    _, tokens = await auth_service.verify_otp_and_login(
        db,
        redis,
        phone=payload.phone,
        otp=payload.otp,
        full_name=payload.full_name,
        role=payload.role,
        license_number=payload.license_number,
    )
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    """Xoay vòng token. Dùng lại một refresh token đã tiêu sẽ thu hồi cả phiên của thiết bị đó."""
    return await auth_service.refresh_tokens(db, redis, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, redis: Redis = Depends(get_redis)) -> None:
    """Đăng xuất thiết bị hiện tại. Không lỗi nếu token đã hết hạn — đăng xuất luôn thành công."""
    from app.core.security import REFRESH_TOKEN, decode_token

    try:
        claims = decode_token(payload.refresh_token, expected_type=REFRESH_TOKEN)
    except Exception:
        return None
    await auth_service.logout(redis, claims)
    return None
