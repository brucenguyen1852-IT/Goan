"""Pricing Service — hiện thực hoá công thức tính cước trong bản gọi vốn (mục 3.1):

Cước = Phí nền + Đơn giá/km × Số km + Đơn giá/phút × Số phút + Phụ thu đón xa (>5km)
Áp mức cước tối thiểu theo khung giờ nếu công thức tính ra thấp hơn.
"""

from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.pricing import PricingRule


@dataclass
class FareBreakdown:
    time_band: str
    base_fare: int
    distance_fare: int
    time_fare: int
    surcharge_far_pickup: int
    subtotal_before_min: int
    total_fare: int  # sau khi áp mức tối thiểu


def resolve_time_band(at: datetime) -> str:
    """Xác định khung giờ. Cao điểm đặc biệt (lễ/tết) nên được set qua bảng
    calendar riêng ở Admin — ở đây chỉ minh hoạ logic giờ thường/giờ đêm."""
    t = at.time()
    if time(6, 0) <= t < time(21, 0):
        return "normal"
    return "night"


def get_active_pricing_rule(db: Session, time_band: str) -> PricingRule:
    rule = (
        db.query(PricingRule)
        .filter(PricingRule.time_band == time_band)
        .order_by(PricingRule.effective_from.desc())
        .first()
    )
    if rule:
        return rule
    # Fallback về giá trị mặc định trong config nếu Ops chưa cấu hình DB (môi trường mới/dev)
    defaults = {
        "normal": PricingRule(time_band="normal", base_fee=30_000, per_km=20_000, per_min=500, min_fare=100_000),
        "night": PricingRule(time_band="night", base_fee=30_000, per_km=24_000, per_min=600, min_fare=110_000),
        "peak": PricingRule(time_band="peak", base_fee=30_000, per_km=27_000, per_min=700, min_fare=120_000),
    }
    return defaults[time_band]


def calculate_fare(
    db: Session,
    distance_km: float,
    duration_min: int,
    requested_at: datetime,
    time_band_override: str | None = None,
) -> FareBreakdown:
    time_band = time_band_override or resolve_time_band(requested_at)
    rule = get_active_pricing_rule(db, time_band)

    distance_fare = round(rule.per_km * distance_km)
    time_fare = round(rule.per_min * duration_min)

    surcharge = 0
    if distance_km > settings.FAR_PICKUP_THRESHOLD_KM:
        # 100% phụ thu này thuộc về tài xế — xử lý ở wallet_service, không phải doanh thu nền tảng
        surcharge = settings.FAR_PICKUP_SURCHARGE

    subtotal = rule.base_fee + distance_fare + time_fare + surcharge
    total = max(subtotal, rule.min_fare)

    return FareBreakdown(
        time_band=time_band,
        base_fare=rule.base_fee,
        distance_fare=distance_fare,
        time_fare=time_fare,
        surcharge_far_pickup=surcharge,
        subtotal_before_min=subtotal,
        total_fare=total,
    )
