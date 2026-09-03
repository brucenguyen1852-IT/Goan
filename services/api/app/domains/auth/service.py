"""Auth service: đăng nhập bằng SĐT + OTP. MVP gửi OTP qua log thay vì SMS thật (SPEC 12 Phase 0)."""

import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import UserRole, UserStatus
from app.core.exceptions import AppError, PermissionDeniedError, UnauthorizedError
from app.core.logging import log_event
from app.core.security import (
    REFRESH_TOKEN,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    new_jti,
    new_token_family,
)
from app.domains.auth import tokens as token_store
from app.domains.auth.schemas import TokenPair
from app.domains.users import repository as users_repo
from app.domains.users.models import DriverProfile, User
from app.redis_client import OTP_KEY

logger = logging.getLogger("goan.auth")


async def request_otp(redis: Redis, phone: str) -> str:
    otp = generate_otp()
    await redis.set(OTP_KEY.format(phone=phone), otp, ex=settings.OTP_TTL_SECONDS)
    # Không log OTP ra plaintext ở production.
    log_event(logger, "otp_issued", phone=phone, channel="log_mock")
    if settings.DEBUG:
        logger.debug("DEV OTP %s -> %s", phone, otp)
    return otp


async def _consume_otp(redis: Redis, phone: str, otp: str) -> None:
    key = OTP_KEY.format(phone=phone)
    stored = await redis.get(key)
    if stored is None:
        raise UnauthorizedError("OTP đã hết hạn, vui lòng gửi lại")
    if stored != otp:
        raise UnauthorizedError("OTP không đúng")
    await redis.delete(key)


async def verify_otp_and_login(
    db: AsyncSession,
    redis: Redis,
    *,
    phone: str,
    otp: str,
    full_name: str | None,
    role: UserRole,
    license_number: str | None,
) -> tuple[User, TokenPair]:
    await _consume_otp(redis, phone, otp)

    user = await users_repo.get_user_by_phone(db, phone)
    if user is None:
        if not full_name:
            raise AppError("Cần full_name khi đăng ký lần đầu")
        user = User(phone=phone, full_name=full_name, role=role)
        db.add(user)
        await db.flush()
        if role is UserRole.DRIVER:
            if not license_number:
                raise AppError("Tài xế cần license_number khi đăng ký")
            db.add(DriverProfile(user_id=user.id, license_number=license_number))
        await db.commit()
        await db.refresh(user)
        log_event(logger, "user_registered", user_id=str(user.id), role=role.value)

    if user.status is UserStatus.BANNED:
        raise PermissionDeniedError("Tài khoản đã bị khoá")

    return user, await issue_tokens(redis, user)


async def issue_tokens(redis: Redis, user: User, *, family: str | None = None) -> TokenPair:
    """Cấp cặp token mới. Không truyền family = đăng nhập mới (mở một họ token mới)."""
    family = family or new_token_family()
    jti = new_jti()
    await token_store.register(redis, jti=jti, family=family)
    return TokenPair(
        access_token=create_access_token(str(user.id), user.role.value, family=family),
        refresh_token=create_refresh_token(str(user.id), user.role.value, jti=jti, family=family),
    )


async def refresh_tokens(db: AsyncSession, redis: Redis, refresh_token: str) -> TokenPair:
    """Xoay vòng: token cũ bị tiêu, cấp token mới cùng họ. Dùng lại token cũ = thu hồi cả họ."""
    payload = decode_token(refresh_token, expected_type=REFRESH_TOKEN)
    user_id = str(payload["sub"])
    family = payload.get("fam")

    # Token cấp trước khi có cơ chế xoay vòng thì không có "fam" — chấp nhận một lần rồi
    # nâng cấp sang họ mới, để bản deploy này không đá toàn bộ người dùng ra.
    if not family:
        log_event(logger, "refresh_legacy_token_upgraded", user_id=user_id)
        user = await _load_active_user(db, user_id)
        return await issue_tokens(redis, user)

    if await token_store.is_family_revoked(redis, family):
        raise UnauthorizedError("Phiên đăng nhập đã bị thu hồi, vui lòng đăng nhập lại")

    try:
        await token_store.consume(redis, jti=payload["jti"], family=family, user_id=user_id)
    except token_store.TokenReuseDetected as exc:
        raise UnauthorizedError(str(exc)) from exc

    user = await _load_active_user(db, user_id)
    return await issue_tokens(redis, user, family=family)


async def logout(redis: Redis, access_or_refresh_payload: dict) -> None:
    """Đăng xuất thiết bị hiện tại: thu hồi cả họ token của thiết bị đó."""
    family = access_or_refresh_payload.get("fam")
    if family:
        await token_store.revoke_family(redis, family)
        log_event(
            logger,
            "logout",
            user_id=str(access_or_refresh_payload.get("sub")),
            family=family,
        )


async def _load_active_user(db: AsyncSession, user_id: str) -> User:
    import uuid as _uuid

    user = await users_repo.get_user(db, _uuid.UUID(user_id))
    if user is None or user.status is UserStatus.BANNED:
        raise UnauthorizedError("Không thể làm mới token")
    return user
