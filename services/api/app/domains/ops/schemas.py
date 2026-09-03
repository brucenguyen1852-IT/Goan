"""Schema cho Console vận hành (P1-09, P1-10, P1-11)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import DriverApprovalStatus, OnlineStatus, TripStatus, UserStatus


class FleetDriverOut(BaseModel):
    """Một chấm trên bản đồ Live Ops. Không kèm PII: bản đồ không cần số điện thoại."""

    driver_id: uuid.UUID
    full_name_masked: str | None
    online_status: OnlineStatus
    lat: float | None
    lng: float | None
    rating_avg: Decimal
    total_trips: int
    current_trip_id: uuid.UUID | None = None


class FleetSnapshot(BaseModel):
    taken_at: datetime
    drivers_online: int
    drivers_on_trip: int
    trips_active: int
    drivers: list[FleetDriverOut]


class OpsDriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    driver_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    phone_masked: str | None
    national_id_masked: str | None
    national_id_verified: bool
    license_number: str
    approval_status: DriverApprovalStatus
    approval_note: str | None = None
    approved_at: datetime | None = None
    account_status: UserStatus
    online_status: OnlineStatus
    rating_avg: Decimal
    total_trips: int
    fraud_strikes: int
    escrow_balance: Decimal


class DecisionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500, description="Lý do, gửi kèm cho tài xế")


class ApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class OpsTripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: TripStatus
    rider_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    pickup_address: str | None = None
    dropoff_address: str | None = None
    distance_km: Decimal | None = None
    estimated_fare: Decimal | None = None
    final_fare: Decimal | None = None
    driver_payout: Decimal | None = None
    requested_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None


class OpsTripPage(BaseModel):
    items: list[OpsTripOut]
    next_cursor: str | None = None


class GpsPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lat: float
    lng: float
    recorded_at: datetime
