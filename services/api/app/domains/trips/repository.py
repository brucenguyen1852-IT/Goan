import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import haversine_km
from app.domains.trips.models import Trip, TripGpsLog, TripRating


async def get_trip(db: AsyncSession, trip_id: uuid.UUID) -> Trip | None:
    return await db.get(Trip, trip_id)


async def get_trip_by_idempotency_key(db: AsyncSession, key: str) -> Trip | None:
    stmt = select(Trip).where(Trip.idempotency_key == key)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_trips_for_user(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int = 20, before: datetime | None = None
) -> list[Trip]:
    """Lịch sử chuyến, mới nhất trước. Phân trang bằng con trỏ thời gian, không dùng OFFSET.

    OFFSET chậm dần khi dữ liệu lớn và có thể bỏ sót/lặp bản ghi khi có chuyến mới chen vào
    giữa hai lần gọi.
    """
    stmt = select(Trip).where(or_(Trip.rider_id == user_id, Trip.driver_id == user_id))
    if before is not None:
        stmt = stmt.where(Trip.requested_at < before)
    stmt = stmt.order_by(Trip.requested_at.desc()).limit(min(limit, 100))
    return list((await db.execute(stmt)).scalars().all())


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


async def get_rating(db: AsyncSession, trip_id: uuid.UUID) -> TripRating | None:
    stmt = select(TripRating).where(TripRating.trip_id == trip_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def driver_rating_stats(db: AsyncSession, driver_id: uuid.UUID) -> tuple[Decimal, int]:
    """Trung bình và số lượt đánh giá của một tài xế, tính lại từ đầu.

    Cộng dồn tăng dần thì mọi lần sửa hoặc xoá đánh giá về sau đều làm lệch vĩnh viễn và
    không đối chiếu lại được. Số lượt đánh giá mỗi tài xế không lớn nên tính lại là đủ rẻ.
    """
    row = (
        await db.execute(
            select(func.avg(TripRating.stars), func.count(TripRating.id)).where(
                TripRating.driver_id == driver_id
            )
        )
    ).one()
    average, total = row[0], int(row[1] or 0)
    if not total:
        return Decimal("0.00"), 0
    return Decimal(str(average)).quantize(Decimal("0.01")), total
