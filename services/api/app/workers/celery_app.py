"""Celery app + beat schedule (SPEC 9, 12)."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "goan",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=5,
    # Tiến trình web cũng đẩy việc vào hàng đợi (push chat, P2-13). Broker chết mà không đặt
    # hạn kết nối thì mỗi lần gửi tin nhắn treo 6 giây trước khi bỏ cuộc — người dùng thấy
    # ứng dụng đơ, vì một dịch vụ chỉ phục vụ việc phụ.
    broker_connection_timeout=1.0,
    broker_connection_retry_on_startup=False,
    broker_transport_options={"socket_connect_timeout": 1, "socket_timeout": 1},
)

celery_app.conf.beat_schedule = {
    "release-wallet-pending": {
        "task": "app.workers.tasks.release_wallet_pending",
        "schedule": crontab(minute="*/15"),
    },
    "expire-stale-matching": {
        "task": "app.workers.tasks.expire_stale_matching",
        "schedule": 60.0,
    },
    "daily-reconciliation": {
        "task": "app.workers.tasks.daily_reconciliation",
        "schedule": crontab(hour=1, minute=0),
    },
    "scan-off-app-signals": {
        "task": "app.workers.tasks.scan_off_app_signals",
        "schedule": crontab(hour=2, minute=0),
    },
    "expire-stale-approvals": {
        "task": "app.workers.tasks.expire_stale_approvals",
        "schedule": crontab(minute="*/30"),
    },
    "close-stale-chat": {
        "task": "app.workers.tasks.close_stale_chat_conversations",
        "schedule": crontab(minute=30),
    },
    # SLA `urgent` là 2 phút, nên quét mỗi phút: quét thưa hơn thì cam kết gắt nhất trở
    # thành thứ không bao giờ đo được.
    "escalate-overdue-tickets": {
        "task": "app.workers.tasks.escalate_overdue_tickets",
        "schedule": crontab(minute="*"),
    },
    "release-offline-agent-tickets": {
        "task": "app.workers.tasks.release_offline_agent_tickets",
        "schedule": crontab(minute="*/5"),
    },
    "purge-orphan-attachments": {
        "task": "app.workers.tasks.purge_orphan_attachments",
        "schedule": crontab(hour=4, minute=0),
    },
    "anonymize-expired-chat": {
        "task": "app.workers.tasks.anonymize_expired_chat",
        "schedule": crontab(hour=4, minute=30),
    },
    "process-escrow-refunds": {
        "task": "app.workers.tasks.process_escrow_refunds",
        "schedule": crontab(hour=3, minute=0),
    },
}
