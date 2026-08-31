"""Notification service: đẩy sự kiện realtime qua WS (+ chỗ cắm push/SMS thật sau này).

Lỗi kênh thông báo KHÔNG được làm hỏng giao dịch nghiệp vụ đã commit (tiền, trạng thái chuyến),
nên mọi lỗi gửi đều được nuốt và ghi log.
"""

import logging
import uuid
from typing import Any

from app.core.logging import log_event
from app.websocket.connection_manager import manager
from app.websocket.events import ServerEvent, server_message

logger = logging.getLogger("goan.notifications")


async def notify_user(user_id: uuid.UUID | str, event: ServerEvent, **payload: Any) -> None:
    try:
        await manager.send_to_user(user_id, server_message(event, **payload))
        log_event(logger, "notify", user_id=str(user_id), event=event.value)
    except Exception:
        logger.warning("notify failed user=%s event=%s", user_id, event.value, exc_info=True)


async def notify_users(user_ids: list[uuid.UUID | str], event: ServerEvent, **payload: Any) -> None:
    for user_id in user_ids:
        await notify_user(user_id, event, **payload)


async def send_push(user_id: uuid.UUID | str, title: str, body: str) -> None:
    """TODO: tích hợp FCM/APNs. MVP chỉ log để không chặn luồng nghiệp vụ."""
    log_event(logger, "push_mock", user_id=str(user_id), title=title, body=body)
