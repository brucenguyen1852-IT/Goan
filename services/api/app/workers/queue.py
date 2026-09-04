"""Đẩy việc vào hàng đợi từ tiến trình web, an toàn khi không có broker.

Đây là ranh giới giữa "việc đã xong" và "việc gửi kèm". Tin nhắn đã ghi vào DB rồi; broker
chết thì người nhận nhận thông báo muộn, chứ tuyệt đối không được mất tin hay trả lỗi 500 cho
người gửi. Vì thế mọi lỗi ở đây đều bị nuốt và ghi log — giống hệt cách `notifications`
xử lý lỗi WebSocket.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.logging import log_event
from app.workers.celery_app import celery_app

logger = logging.getLogger("goan.queue")


def enqueue(task_name: str, *args: Any, countdown: int = 0) -> bool:
    """Trả về True nếu đã đẩy được vào hàng đợi. Không ném ngoại lệ trong mọi trường hợp."""
    try:
        # `retry=False`: không có broker thì phải biết ngay. Để kombu thử lại nghĩa là giữ
        # request của người dùng trong lúc chờ một dịch vụ đang chết.
        celery_app.send_task(task_name, args=list(args), countdown=countdown, retry=False)
        return True
    except Exception:
        log_event(logger, "enqueue_failed", task=task_name)
        return False
