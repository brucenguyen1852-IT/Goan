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
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await auth_service.refresh_tokens(db, payload.refresh_token)
