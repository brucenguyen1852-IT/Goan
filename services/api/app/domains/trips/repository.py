import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import haversine_km
from app.domains.trips.models import Trip, TripGpsLog


async def get_trip(db: AsyncSession, trip_id: uuid.UUID) -> Trip | None:
    return await db.get(Trip, trip_id)


async def get_trip_by_idempotency_key(db: AsyncSession, key: str) -> Trip | None:
    stmt = select(Trip).where(Trip.idempotency_key == key)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_gps_logs(db: AsyncSession, trip_id: uuid.UUID) -> list[TripGpsLog]:
    stmt = (
        select(TripGpsLog)
        .where(TripGpsLog.trip_id == trip_id)
        .order_by(TripGpsLog.recorded_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def add_gps_log(
    db: AsyncSession, trip_id: uuid.UUID, lat: float, lng: float, recorded_at: datetime
) -> TripGpsLog:
    log = TripGpsLog(trip_id=trip_id, lat=lat, lng=lng, recorded_at=recorded_at)
    db.add(log)
    await db.flush()
    return log


def total_gps_distance_km(points: list[TripGpsLog]) -> Decimal:
    """Tổng quãng đường thực tế từ chuỗi GPS log (SPEC 7.2)."""
    total = Decimal("0")
    for prev, cur in zip(points, points[1:], strict=False):  # lệch 1 phần tử là cố ý
        total += haversine_km(prev.lat, prev.lng, cur.lat, cur.lng)
    return total.quantize(Decimal("0.01"))
