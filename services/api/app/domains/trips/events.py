"""Ghi dấu vết vòng đời chuyến (SPEC 4 — bảng trip_events).

Hàm ở đây KHÔNG commit: chúng chạy trong transaction của caller, để dấu vết và thay đổi
trạng thái cùng sống hoặc cùng chết. Một dòng thời gian nói chuyến đã hoàn thành trong khi
transaction đã rollback còn tệ hơn là không có dòng nào.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TripActorType, TripEventType, TripStatus
from app.domains.trips.models import TripEvent

logger = logging.getLogger("goan.trips.events")


async def record(
    db: AsyncSession,
    trip_id: uuid.UUID,
    event_type: TripEventType,
    *,
    from_status: TripStatus | None = None,
    to_status: TripStatus | None = None,
    actor_type: TripActorType = TripActorType.SYSTEM,
    actor_id: uuid.UUID | None = None,
    **payload: Any,
) -> TripEvent:
    event = TripEvent(
        trip_id=trip_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_type=actor_type,
        actor_id=actor_id,
        payload=payload,
    )
    db.add(event)
    await db.flush()
    return event


async def list_for_trip(db: AsyncSession, trip_id: uuid.UUID) -> list[TripEvent]:
    stmt = (
        select(TripEvent)
        .where(TripEvent.trip_id == trip_id)
        .order_by(TripEvent.created_at.asc(), TripEvent.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())
