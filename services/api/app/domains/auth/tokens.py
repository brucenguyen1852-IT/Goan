"""Xoay vòng refresh token và phát hiện tái sử dụng (OAuth 2.0 BCP, mục 4.13).

Vấn đề: refresh token sống 30 ngày. Nếu bị lộ (máy mất, log rò, proxy bẩn) thì kẻ lấy được
dùng vô tư suốt 30 ngày mà hệ thống không biết.

Cách xử lý:
  - Mỗi lần đăng nhập tạo một "họ" token (family) — tương ứng một thiết bị.
  - Mỗi lần refresh: token cũ bị đánh dấu ĐÃ TIÊU, cấp token mới cùng họ.
  - Nếu một token ĐÃ TIÊU được dùng lại → chắc chắn có hai bên cùng giữ token → thu hồi
    CẢ HỌ. Cả kẻ tấn công lẫn người dùng thật đều bị đăng xuất; người dùng thật đăng nhập
    lại bằng OTP, kẻ tấn công thì không có số điện thoại.

Đánh đổi đã cân nhắc: khi Redis chết, hàm này cho refresh đi qua thay vì chặn. Lý do —
Redis chết thì matching, vị trí tài xế và rate limit đều chết, hệ thống coi như dừng; chặn
thêm refresh chỉ làm mọi người bị đăng xuất hàng loạt mà không tăng an toàn thực tế. Mỗi lần
đi qua như vậy đều ghi log mức WARNING để đội vận hành thấy.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.config import settings
from app.core.logging import log_event

logger = logging.getLogger("goan.auth.tokens")

ACTIVE_KEY = "refresh:active:{jti}"
USED_KEY = "refresh:used:{jti}"
FAMILY_REVOKED_KEY = "refresh:revoked_family:{family}"


def _ttl_seconds() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


class TokenReuseDetected(Exception):
    """Một refresh token đã tiêu bị dùng lại — cả họ token đã bị thu hồi."""


async def register(redis: Redis, *, jti: str, family: str) -> None:
    ttl = _ttl_seconds()
    try:
        await redis.set(ACTIVE_KEY.format(jti=jti), family, ex=ttl)
    except Exception:
        logger.warning("Redis lỗi khi đăng ký refresh token, bỏ qua", exc_info=True)


async def revoke_family(redis: Redis, family: str) -> None:
    try:
        await redis.set(FAMILY_REVOKED_KEY.format(family=family), "1", ex=_ttl_seconds())
    except Exception:
        logger.warning("Redis lỗi khi thu hồi họ token", exc_info=True)


async def is_family_revoked(redis: Redis, family: str) -> bool:
    try:
        return bool(await redis.exists(FAMILY_REVOKED_KEY.format(family=family)))
    except Exception:
        logger.warning("Redis lỗi khi kiểm tra họ token, cho qua", exc_info=True)
        return False


async def consume(redis: Redis, *, jti: str, family: str, user_id: str) -> None:
    """Tiêu một refresh token. Ném TokenReuseDetected nếu nó đã bị tiêu trước đó."""
    used_key = USED_KEY.format(jti=jti)
    try:
        already_used = await redis.exists(used_key)
    except Exception:
        logger.warning("Redis lỗi khi kiểm tra token đã tiêu, cho qua", exc_info=True)
        return

    if already_used:
        await revoke_family(redis, family)
        log_event(
            logger,
            "refresh_token_reuse_detected",
            user_id=user_id,
            family=family,
            action="revoked_whole_family",
        )
        raise TokenReuseDetected(
            "Refresh token đã được sử dụng trước đó — toàn bộ phiên đăng nhập của thiết bị này đã bị thu hồi"
        )

    try:
        await redis.set(used_key, "1", ex=_ttl_seconds())
        await redis.delete(ACTIVE_KEY.format(jti=jti))
    except Exception:
        logger.warning("Redis lỗi khi đánh dấu token đã tiêu", exc_info=True)
