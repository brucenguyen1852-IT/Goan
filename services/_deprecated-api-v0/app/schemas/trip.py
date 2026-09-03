from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    lat: float
    lng: float


class FareEstimateIn(BaseModel):
    pickup: GeoPoint
    dropoff: GeoPoint
    pickup_address: str
    dropoff_address: str


class FareEstimateOut(BaseModel):
    time_band: str
    distance_km: float
    duration_min: int
    base_fare: int
    distance_fare: int
    time_fare: int
    surcharge_far_pickup: int
    total_fare_estimate: int


class TripCreateIn(BaseModel):
    pickup: GeoPoint
    dropoff: GeoPoint
    pickup_address: str
    dropoff_address: str
    payment_method: str = Field(..., pattern="^(online|cash)$")
    partner_qr_code: str | None = None


class TripOut(BaseModel):
    id: UUID
    status: str
    pickup_address: str
    dropoff_address: str
    total_fare: int | None
    driver_id: UUID | None
    requested_at: datetime

    class Config:
        from_attributes = True


class QrVerifyIn(BaseModel):
    qr_token: str
