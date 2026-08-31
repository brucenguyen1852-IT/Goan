import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.constants import EscrowStatus, OnlineStatus, UserRole, UserStatus


class UserOut(BaseModel):
    id: uuid.UUID
    phone: str
    full_name: str
    role: UserRole
    status: UserStatus
    national_id_verified: bool
    national_id_masked: str | None = None
    avatar_url: str | None = None


class DriverProfileOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    license_number: str
    license_years_experience: int | None
    online_status: OnlineStatus
    escrow_balance: Decimal
    escrow_target: Decimal
    escrow_status: EscrowStatus
    rating_avg: Decimal
    total_trips: int
    fraud_strikes: int


class GoOnlineResponse(BaseModel):
    online_status: OnlineStatus
    qr_token: str  # tài xế render QR này, rider quét để bắt đầu chuyến (SPEC 7.1)


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class EkycSubmit(BaseModel):
    national_id_number: str = Field(min_length=9, max_length=20)
    selfie_reference_url: str


class EkycResult(BaseModel):
    national_id_verified: bool
    national_id_masked: str | None


class SelfieCheckSubmit(BaseModel):
    selfie_url: str


class SelfieCheckResult(BaseModel):
    passed: bool
    match_score: float
    account_status: UserStatus
