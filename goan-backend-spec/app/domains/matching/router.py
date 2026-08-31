import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.deps import get_current_driver, get_redis
from app.domains.matching import service as matching_service
from app.domains.partners import service as partners_service
from app.domains.trips import repository as trips_repo
from app.domains.trips.schemas import TripOut
from app.domains.users.models import User

router = APIRouter(prefix="/matching", tags=["matching"])


class HeatmapZone(BaseModel):
    id: uuid.UUID
    name: str
    lat: float
    lng: float
    radius_m: int
    is_new_zone: bool
    active_hours: dict


@router.post("/trips/{trip_id}/accept", response_model=TripOut)
async def accept_trip(
    trip_id: uuid.UUID,
    driver: User = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TripOut:
    """Tài xế nhận chuyến (fallback HTTP của event WS `trip_offer_response`)."""
    trip = await trips_repo.get_trip(db, trip_id)
    if trip is None:
        raise NotFoundError("Không tìm thấy chuyến")
    trip = await matching_service.accept_offer(db, redis, trip, driver.id)
    return TripOut.model_validate(trip)


@router.get("/heatmap", response_model=list[HeatmapZone])
async def satellite_heatmap(
    _: User = Depends(get_current_driver), db: AsyncSession = Depends(get_db)
) -> list[HeatmapZone]:
    """Gợi ý vị trí trực vệ tinh cho driver app (SPEC 6.4a)."""
    zones = await partners_service.list_satellite_zones(db)
    return [
        HeatmapZone(
            id=z.id,
            name=z.name,
            lat=z.lat,
            lng=z.lng,
            radius_m=z.radius_m,
            is_new_zone=z.is_new_zone,
            active_hours=z.active_hours or {},
        )
        for z in zones
    ]
