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
    "process-escrow-refunds": {
        "task": "app.workers.tasks.process_escrow_refunds",
        "schedule": crontab(hour=3, minute=0),
    },
}
