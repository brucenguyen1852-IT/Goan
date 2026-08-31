from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.domains.pricing import service as pricing_service
from app.domains.pricing.schemas import FareEstimateRequest, FareEstimateResponse

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.post("/estimate", response_model=FareEstimateResponse)
async def estimate_fare(
    payload: FareEstimateRequest, db: AsyncSession = Depends(get_db)
) -> FareEstimateResponse:
    """Trả giá ước tính TRƯỚC khi rider xác nhận đặt (SPEC 4.5)."""
    requested_at = payload.requested_at or datetime.now(timezone.utc)
    time_band = await pricing_service.resolve_time_band_db(db, requested_at)
    rule = await pricing_service.get_fare_rule(db, time_band)
    distance_km, duration_minutes = pricing_service.estimate_distance_and_duration(
        payload.pickup.lat, payload.pickup.lng, payload.dropoff.lat, payload.dropoff.lng
    )
    breakdown = pricing_service.calculate_fare(
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        time_band=time_band,
        driver_to_pickup_distance_km=payload.driver_to_pickup_distance_km,
        rule=rule,
    )
    return FareEstimateResponse(
        time_band=time_band,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        breakdown=breakdown,
    )
