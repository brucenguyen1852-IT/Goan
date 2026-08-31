"""Dependencies dùng chung (SPEC 2)."""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole, UserStatus
from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.security import decode_token
from app.database import get_db
from app.domains.users.models import DriverProfile, User
from app.redis_client import get_redis as _get_redis

# Bearer scheme: trên Swagger UI chỉ cần bấm Authorize và dán access_token lấy từ /auth/verify-otp.
bearer_scheme = HTTPBearer(auto_error=False, description="Dán access_token từ /api/v1/auth/verify-otp")


async def get_redis() -> Redis:
    return _get_redis()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Thiếu access token")
    payload = decode_token(credentials.credentials)
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise UnauthorizedError("Người dùng không tồn tại")
    if user.status is UserStatus.BANNED:
        raise PermissionDeniedError("Tài khoản đã bị khoá")
    return user


async def get_current_rider(user: User = Depends(get_current_user)) -> User:
    if user.role is not UserRole.RIDER:
        raise PermissionDeniedError("Chỉ khách hàng mới được thao tác")
    return user


async def get_current_driver(user: User = Depends(get_current_user)) -> User:
    if user.role is not UserRole.DRIVER:
        raise PermissionDeniedError("Chỉ tài xế mới được thao tác")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role is not UserRole.ADMIN:
        raise PermissionDeniedError("Chỉ admin mới được thao tác")
    return user


async def get_driver_profile(
    user: User = Depends(get_current_driver), db: AsyncSession = Depends(get_db)
) -> DriverProfile:
    stmt = select(DriverProfile).where(DriverProfile.user_id == user.id)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if profile is None:
        raise PermissionDeniedError("Tài xế chưa có hồ sơ")
    return profile
