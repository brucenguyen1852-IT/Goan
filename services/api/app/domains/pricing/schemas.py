from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.constants import TimeBand


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class FareBreakdown(BaseModel):
    """Breakdown đầy đủ theo SPEC 4.4.

    Lưu ý phân bổ: `insurance_fee` và `payment_gateway_fee` được trừ TRONG phần
    `platform_commission` (nền tảng giữ), không thu thêm của rider.
    """

    base_fee: Decimal
    distance_fee: Decimal
    time_fee: Decimal
    pickup_surcharge: Decimal
    subtotal: Decimal
    final_fare: Decimal  # sau khi áp cước tối thiểu
    driver_payout: Decimal  # ~58% + 100% phụ thu đón xa
    platform_commission: Decimal
    insurance_fee: Decimal
    payment_gateway_fee: Decimal


class FareEstimateRequest(BaseModel):
    pickup: Coordinate
    dropoff: Coordinate
    requested_at: datetime | None = None
    driver_to_pickup_distance_km: Decimal | None = None


class FareEstimateResponse(BaseModel):
    time_band: TimeBand
    distance_km: Decimal
    duration_minutes: int
    breakdown: FareBreakdown
