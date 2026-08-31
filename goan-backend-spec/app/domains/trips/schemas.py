import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import TimeBand, TripStatus
from app.domains.pricing.schemas import Coordinate, FareBreakdown


class TripCreate(BaseModel):
    pickup: Coordinate
    pickup_address: str | None = None
    dropoff: Coordinate
    dropoff_address: str | None = None
    restaurant_partner_qr_token: str | None = None  # đặt xe tại bàn (SPEC 10.1)
    idempotency_key: str | None = Field(default=None, max_length=64)


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rider_id: uuid.UUID
    driver_id: uuid.UUID | None
    status: TripStatus
    time_band: TimeBand
    pickup_lat: float
    pickup_lng: float
    pickup_address: str | None
    dropoff_lat: float | None
    dropoff_lng: float | None
    dropoff_address: str | None
    estimated_fare: Decimal | None
    final_fare: Decimal | None
    distance_km: Decimal | None
    optimal_distance_km: Decimal | None
    duration_minutes: int | None
    pickup_surcharge: Decimal
    platform_commission: Decimal | None
    driver_payout: Decimal | None
    insurance_fee: Decimal | None
    insurance_voided: bool
    cancellation_fee: Decimal
    qr_verified_at: datetime | None
    requested_at: datetime | None
    matched_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None


class TripCreateResponse(BaseModel):
    trip: TripOut
    estimate: FareBreakdown


class VerifyQrRequest(BaseModel):
    qr_token: str


class CompleteTripRequest(BaseModel):
    lat: float | None = None
    lng: float | None = None
    idempotency_key: str | None = Field(default=None, max_length=64)


class CompleteTripResponse(BaseModel):
    trip: TripOut
    fare: FareBreakdown
    driver_actual_payout: Decimal  # sau khi trích ký quỹ
    escrow_deducted: Decimal
    route_deviation_detected: bool


class CancelTripRequest(BaseModel):
    reason: str | None = None


class GpsPing(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    recorded_at: datetime | None = None


class GpsPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lat: float
    lng: float
    recorded_at: datetime
