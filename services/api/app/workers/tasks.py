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


@celery_app.task(name="app.workers.tasks.expire_stale_approvals")
def expire_stale_approvals() -> int:
    """Đóng các đề nghị chạm tiền đã quá hạn (P1-07)."""
    from app.domains.approvals import service as approvals_service

    async def run(db):
        return await approvals_service.expire_due(db)

    return _run(run)


@celery_app.task(name="app.workers.tasks.close_stale_chat_conversations")
def close_stale_chat_conversations() -> int:
    """Đóng hội thoại của chuyến đã kết thúc quá 24 giờ (P2-07)."""
    from app.domains.chat import service as chat_service

    async def run(db):
        return await chat_service.close_stale_trip_conversations(db)

    return _run(run)


@celery_app.task(name="app.workers.tasks.escalate_overdue_tickets")
def escalate_overdue_tickets() -> int:
    """Ticket quá hạn phản hồi đầu thì tự leo thang lên cs_lead (P2-08)."""
    from app.domains.support import service as support_service

    async def run(db):
        return await support_service.escalate_overdue(db)

    return _run(run)


@celery_app.task(name="app.workers.tasks.release_offline_agent_tickets")
def release_offline_agent_tickets() -> int:
    """Agent tắt máy giữa ca thì ticket của họ quay về hàng đợi (P2-08, bàn giao ca)."""
    from app.domains.support import service as support_service

    async def run(db):
        return await support_service.release_offline_agents(db)

    return _run(run)


@celery_app.task(name="app.workers.tasks.purge_orphan_attachments")
def purge_orphan_attachments() -> int:
    """Dọn tệp đã xin URL nhưng không bao giờ được gửi (P2-12)."""
    from app.domains.chat import service as chat_service

    async def run(db):
        return await chat_service.purge_orphan_attachments(db)

    return _run(run)


@celery_app.task(name="app.workers.tasks.deliver_chat_push")
def deliver_chat_push(message_id: str, user_id: str) -> int:
    """Push cho người nhận nếu sau vài giây họ vẫn chưa đọc (P2-13)."""
    import uuid as _uuid

    from app.domains.chat import service as chat_service

    async def run(db):
        return await chat_service.deliver_offline_push(
            db, _uuid.UUID(message_id), _uuid.UUID(user_id)
        )

    return _run(run)


@celery_app.task(name="app.workers.tasks.anonymize_expired_chat")
def anonymize_expired_chat() -> int:
    """Ẩn danh hoá hội thoại quá hạn lưu trữ 12/24 tháng (P2-20)."""
    from app.domains.chat import service as chat_service

    async def run(db):
        return await chat_service.anonymize_expired_conversations(db)

    return _run(run)
