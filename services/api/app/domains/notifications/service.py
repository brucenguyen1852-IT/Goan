"""Notification service: đẩy sự kiện realtime qua WS (+ chỗ cắm push/SMS thật sau này).

Lỗi kênh thông báo KHÔNG được làm hỏng giao dịch nghiệp vụ đã commit (tiền, trạng thái chuyến),
nên mọi lỗi gửi đều được nuốt và ghi log.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log_event
from app.domains.notifications.constants import DevicePlatform
from app.domains.notifications.models import PushToken
from app.domains.users.models import User
from app.integrations.push import get_push
from app.websocket.connection_manager import manager
from app.websocket.events import ServerEvent, server_message

logger = logging.getLogger("goan.notifications")


async def notify_user(user_id: uuid.UUID | str, event: ServerEvent, **payload: Any) -> None:
    try:
        await manager.send_to_user(user_id, server_message(event, **payload))
        log_event(logger, "notify", user_id=str(user_id), event=event.value)
    except Exception:
        logger.warning("notify failed user=%s event=%s", user_id, event.value, exc_info=True)


async def notify_users(
    user_ids: Sequence[uuid.UUID | str], event: ServerEvent, **payload: Any
) -> None:
    for user_id in user_ids:
        await notify_user(user_id, event, **payload)


# --- Push tới thiết bị (P2-13) --------------------------------------------------------


async def register_push_token(
    db: AsyncSession, user: User, *, token: str, platform: DevicePlatform
) -> PushToken:
    """Đăng ký token thiết bị. Cùng token đăng ký lại thì cập nhật, không tạo dòng thứ hai.

    Token có thể chuyển chủ: người dùng đăng xuất rồi người khác đăng nhập trên cùng máy.
    Không đổi `user_id` theo là gửi tin nhắn của người này tới màn hình khoá của người kia.
    """
    row = (await db.execute(select(PushToken).where(PushToken.token == token))).scalar_one_or_none()
    if row is None:
        row = PushToken(user_id=user.id, token=token, platform=platform)
        db.add(row)
    row.user_id = user.id
    row.platform = platform
    row.is_active = True
    row.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def revoke_push_token(db: AsyncSession, token: str) -> None:
    """Đăng xuất thì gỡ token khỏi máy đó, không đụng tới các máy khác của cùng người."""
    row = (await db.execute(select(PushToken).where(PushToken.token == token))).scalar_one_or_none()
    if row is not None:
        row.is_active = False
        await db.commit()


async def active_tokens(db: AsyncSession, user_id: uuid.UUID) -> list[PushToken]:
    return list(
        (
            await db.execute(
                select(PushToken).where(PushToken.user_id == user_id, PushToken.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )


async def send_push(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> int:
    """Gửi push tới mọi thiết bị còn hiệu lực của một người. Trả về số máy nhận được.

    Token bị nhà cung cấp báo chết thì gỡ ngay tại đây: giữ lại nghĩa là mỗi tin nhắn về sau
    tốn thêm một lời gọi mạng chắc chắn thất bại, nhân với số người dùng đã cài lại app.
    """
    rows = await active_tokens(db, uuid.UUID(str(user_id)))
    if not rows:
        return 0
    try:
        ket_qua = await get_push().send([r.token for r in rows], title=title, body=body, data=data)
    except Exception:
        # Push hỏng KHÔNG được làm hỏng việc đã xong: tin nhắn đã nằm trong DB rồi.
        logger.warning("push failed user=%s", user_id, exc_info=True)
        return 0
    if ket_qua.invalid_tokens:
        hong = set(ket_qua.invalid_tokens)
        for row in rows:
            if row.token in hong:
                row.is_active = False
        await db.commit()
        log_event(logger, "push_tokens_revoked", count=len(hong), user_id=str(user_id))
    for row in rows:
        if row.token not in set(ket_qua.invalid_tokens):
            row.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    log_event(logger, "push_delivered", user_id=str(user_id), count=ket_qua.delivered)
    return ket_qua.delivered
