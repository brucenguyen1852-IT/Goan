"""Pricing service (SPEC 4) — toàn bộ logic tính tiền nằm ở đây, không ở router.

Mọi phép tính dùng Decimal, làm tròn ROUND_HALF_UP về VNĐ nguyên.
"""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import TimeBand
from app.core.geo import haversine_km
from app.core.money import vnd
from app.domains.pricing.constants import (
    DEFAULT_FARE_RULES,
    NORMAL_BAND_END_HOUR,
    NORMAL_BAND_START_HOUR,
    FareRule,
)
from app.domains.pricing.models import PeakPeriod, PricingRule
from app.domains.pricing.schemas import FareBreakdown

LOCAL_TZ = ZoneInfo(settings.LOCAL_TZ)

# Hệ số quy đổi đường chim bay -> quãng đường thực tế và tốc độ trung bình nội đô,
# chỉ dùng cho bước ƯỚC TÍNH trước chuyến. Cước cuối luôn tính theo số liệu thực tế.
ROAD_DISTANCE_FACTOR = Decimal("1.30")
AVG_CITY_SPEED_KMH = Decimal("25")


def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def resolve_time_band(requested_at: datetime, *, is_peak: bool = False) -> TimeBand:
    """Khung giờ chốt tại thời điểm request, tính theo giờ Việt Nam (SPEC 4.1, 13)."""
    if is_peak:
        return TimeBand.PEAK
    hour = _to_local(requested_at).hour
    if NORMAL_BAND_START_HOUR <= hour < NORMAL_BAND_END_HOUR:
        return TimeBand.NORMAL
    return TimeBand.NIGHT


async def is_peak_period(db: AsyncSession, at: datetime) -> bool:
    """Cao điểm đặc biệt: kiểm tra overlap với bảng peak_periods."""
    at_utc = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    stmt = select(PeakPeriod.id).where(
        PeakPeriod.active.is_(True),
        PeakPeriod.start_at <= at_utc,
        PeakPeriod.end_at >= at_utc,
    )
    return (await db.execute(stmt)).first() is not None


async def resolve_time_band_db(db: AsyncSession, requested_at: datetime) -> TimeBand:
    return resolve_time_band(requested_at, is_peak=await is_peak_period(db, requested_at))


async def get_fare_rule(db: AsyncSession, time_band: TimeBand) -> FareRule:
    """Đọc biểu giá từ DB nếu admin đã cấu hình, fallback về hằng số mặc định."""
    stmt = (
        select(PricingRule)
        .where(PricingRule.time_band == time_band, PricingRule.active.is_(True))
        .order_by(PricingRule.effective_from.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return DEFAULT_FARE_RULES[time_band]
    return FareRule(
        base_fee=Decimal(row.base_fee),
        per_km=Decimal(row.per_km),
        per_minute=Decimal(row.per_minute),
        min_fare=Decimal(row.min_fare),
    )


def calculate_pickup_surcharge(driver_to_pickup_distance_km: Decimal | None) -> Decimal:
    """<= 5km: không phụ thu. > 5km: +20.000đ, 100% chuyển thẳng cho tài xế (SPEC 4.3)."""
    if driver_to_pickup_distance_km is None:
        return Decimal("0")
    if Decimal(driver_to_pickup_distance_km) > settings.PICKUP_FREE_RADIUS_KM:
        return vnd(settings.PICKUP_SURCHARGE_AMOUNT)
    return Decimal("0")


def calculate_fare(
    *,
    distance_km: Decimal,
    duration_minutes: int,
    time_band: TimeBand,
    driver_to_pickup_distance_km: Decimal | None = None,
    rule: FareRule | None = None,
    take_rate: Decimal | None = None,
    driver_share_rate: Decimal | None = None,
) -> FareBreakdown:
    """cước = phí nền + đơn giá/km × km + đơn giá/phút × phút + phụ thu đón xa;
    cước cuối = MAX(cước, cước tối thiểu theo khung giờ)."""
    rule = rule or DEFAULT_FARE_RULES[time_band]
    take_rate = settings.TAKE_RATE if take_rate is None else take_rate
    driver_share_rate = (
        settings.DRIVER_SHARE_RATE if driver_share_rate is None else driver_share_rate
    )

    distance_km = Decimal(distance_km)
    base_fee = vnd(rule.base_fee)
    distance_fee = vnd(rule.per_km * distance_km)
    time_fee = vnd(rule.per_minute * Decimal(duration_minutes))
    pickup_surcharge = calculate_pickup_surcharge(driver_to_pickup_distance_km)

    subtotal = vnd(base_fee + distance_fee + time_fee + pickup_surcharge)
    final_fare = vnd(max(subtotal, rule.min_fare))

    # Phụ thu đón xa không nằm trong phần chia take-rate: 100% về tài xế.
    fare_ex_surcharge = final_fare - pickup_surcharge
    driver_payout = vnd(fare_ex_surcharge * driver_share_rate + pickup_surcharge)
    platform_commission = vnd(fare_ex_surcharge * take_rate)
    insurance_fee = vnd(final_fare * settings.INSURANCE_FEE_RATE)
    payment_gateway_fee = vnd(final_fare * settings.PAYMENT_GATEWAY_FEE_RATE)

    return FareBreakdown(
        base_fee=base_fee,
        distance_fee=distance_fee,
        time_fee=time_fee,
        pickup_surcharge=pickup_surcharge,
        subtotal=subtotal,
        final_fare=final_fare,
        driver_payout=driver_payout,
        platform_commission=platform_commission,
        insurance_fee=insurance_fee,
        payment_gateway_fee=payment_gateway_fee,
    )


def estimate_distance_and_duration(
    pickup_lat: float, pickup_lng: float, dropoff_lat: float, dropoff_lng: float
) -> tuple[Decimal, int]:
    """Ước tính trước chuyến khi chưa có Directions API (MVP fallback)."""
    straight = haversine_km(pickup_lat, pickup_lng, dropoff_lat, dropoff_lng)
    distance = (straight * ROAD_DISTANCE_FACTOR).quantize(Decimal("0.01"))
    minutes = int((distance / AVG_CITY_SPEED_KMH * Decimal("60")).to_integral_value())
    return distance, max(minutes, 1)
