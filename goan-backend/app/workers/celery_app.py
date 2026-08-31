from celery import Celery

from app.core.config import settings

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
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
)

# Lịch chạy định kỳ (Celery Beat) — payout hàng tuần, hoàn ký quỹ, quét gian lận
celery_app.conf.beat_schedule = {
    "weekly-driver-payout": {
        "task": "app.workers.tasks.run_weekly_payout",
        "schedule": 7 * 24 * 60 * 60,  # 7 ngày — production nên dùng crontab cụ thể thứ 2 hàng tuần
    },
    "check-escrow-refund-eligibility": {
        "task": "app.workers.tasks.check_escrow_refunds",
        "schedule": 24 * 60 * 60,  # chạy mỗi ngày
    },
}
