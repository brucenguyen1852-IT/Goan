"""Task nền: giải phóng ví, đối soát, quét tín hiệu gian lận, hoàn ký quỹ, dọn chuyến treo.

Task chạy trong worker đồng bộ nên dùng `asyncio.run` bao quanh service async.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from app.database import SessionFactory
from app.domains.escrow import service as escrow_service
from app.domains.fraud import service as fraud_service
from app.domains.matching import service as matching_service
from app.domains.payments import service as payments_service
from app.workers.celery_app import celery_app

logger = logging.getLogger("goan.workers")


def _run(coro_factory: Callable[..., Coroutine[Any, Any, Any]]) -> Any:
    async def runner() -> Any:
        async with SessionFactory() as db:
            return await coro_factory(db)

    return asyncio.run(runner())


@celery_app.task(name="app.workers.tasks.release_wallet_pending", bind=True, max_retries=5)
def release_wallet_pending(self) -> int:
    try:
        return _run(payments_service.release_pending_balances)
    except Exception as exc:  # pragma: no cover - retry theo cấu hình Celery
        raise self.retry(exc=exc) from exc


@celery_app.task(name="app.workers.tasks.daily_reconciliation", bind=True, max_retries=5)
def daily_reconciliation(self) -> str:
    try:
        report = _run(payments_service.run_daily_reconciliation)
        return report.report_date.isoformat()
    except Exception as exc:  # pragma: no cover
        raise self.retry(exc=exc) from exc


@celery_app.task(name="app.workers.tasks.scan_off_app_signals")
def scan_off_app_signals() -> int:
    flagged = _run(fraud_service.scan_off_app_payment_signals)
    return len(flagged)


@celery_app.task(name="app.workers.tasks.process_escrow_refunds", bind=True, max_retries=5)
def process_escrow_refunds(self) -> int:
    try:
        return _run(escrow_service.process_due_refunds)
    except Exception as exc:  # pragma: no cover
        raise self.retry(exc=exc) from exc


@celery_app.task(name="app.workers.tasks.expire_stale_matching")
def expire_stale_matching() -> int:
    return _run(matching_service.expire_stale_matching_trips)
