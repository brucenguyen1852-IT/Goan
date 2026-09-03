import uuid

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_driver, get_current_rider, get_current_user, get_redis
from app.domains.matching import service as matching_service
from app.domains.trips import repository as trips_repo
from app.domains.trips import service as trips_service
from app.domains.trips.schemas import (
    CancelTripRequest,
    CompleteTripRequest,
    CompleteTripResponse,
    GpsPing,
    GpsPointOut,
    TripCreate,
    TripCreateResponse,
    TripOut,
    VerifyQrRequest,
)
from app.domains.users.models import User

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    payload: TripCreate,
    rider: User = Depends(get_current_rider),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TripCreateResponse:
    trip, estimate = await trips_service.create_trip(db, rider, payload)
    await matching_service.start_matching(db, redis, trip)
    return TripCreateResponse(trip=TripOut.model_validate(trip), estimate=estimate)


@router.get("/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/cancel", response_model=TripOut)
async def cancel_trip(
    trip_id: uuid.UUID,
    payload: CancelTripRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    trip = await trips_service.cancel_trip(db, trip, user, payload.reason)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/verify-qr", response_model=TripOut)
async def verify_qr(
    trip_id: uuid.UUID,
    payload: VerifyQrRequest,
    rider: User = Depends(get_current_rider),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    """Rider quét QR tài xế -> qr_verified -> in_progress (SPEC 7.1)."""
    trip = await trips_service.get_trip_for_user(db, trip_id, rider)
    trip = await trips_service.verify_qr(db, trip, rider, payload.qr_token)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/complete", response_model=CompleteTripResponse)
async def complete_trip(
    trip_id: uuid.UUID,
    payload: CompleteTripRequest,
    driver: User = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
) -> CompleteTripResponse:
    trip = await trips_service.get_trip_for_user(db, trip_id, driver)
    result = await trips_service.complete_trip(
        db,
        trip,
        driver,
        lat=payload.lat,
        lng=payload.lng,
        idempotency_key=payload.idempotency_key,
    )
    return CompleteTripResponse(
        trip=TripOut.model_validate(result.trip),
        fare=result.fare,
        driver_actual_payout=result.driver_actual_payout,
        escrow_deducted=result.escrow_deducted,
        route_deviation_detected=result.route_deviation_detected,
    )


@router.get("/{trip_id}/gps-history", response_model=list[GpsPointOut])
async def gps_history(
    trip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GpsPointOut]:
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    points = await trips_repo.list_gps_logs(db, trip.id)
    return [GpsPointOut.model_validate(p) for p in points]


@router.post("/{trip_id}/gps-ping", status_code=status.HTTP_204_NO_CONTENT)
async def gps_ping(
    trip_id: uuid.UUID,
    payload: GpsPing,
    driver: User = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
) -> None:
    trip = await trips_service.get_trip_for_user(db, trip_id, driver)
    await trips_service.record_gps_ping(
        db, trip, driver, payload.lat, payload.lng, payload.recorded_at
    )
