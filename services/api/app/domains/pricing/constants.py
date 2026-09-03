"""Biểu giá mặc định (SPEC 4.1) — hard-code đúng con số deck, override được qua bảng `pricing_rules`.

| Hạng mục            | Giờ thường 06-21h | Giờ đêm 21-05h | Cao điểm |
|---------------------|-------------------|----------------|----------|
| Phí nền (gồm BH)    | 30.000            | 30.000         | 30.000   |
| Đơn giá / km        | 20.000            | 24.000         | 27.000   |
| Đơn giá / phút      | 500               | 600            | 700      |
| Cước tối thiểu/đơn  | 100.000           | 110.000        | 120.000  |
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.constants import TimeBand


@dataclass(frozen=True)
class FareRule:
    base_fee: Decimal
    per_km: Decimal
    per_minute: Decimal
    min_fare: Decimal


DEFAULT_FARE_RULES: dict[TimeBand, FareRule] = {
    TimeBand.NORMAL: FareRule(
        base_fee=Decimal("30000"),
        per_km=Decimal("20000"),
        per_minute=Decimal("500"),
        min_fare=Decimal("100000"),
    ),
    TimeBand.NIGHT: FareRule(
        base_fee=Decimal("30000"),
        per_km=Decimal("24000"),
        per_minute=Decimal("600"),
        min_fare=Decimal("110000"),
    ),
    TimeBand.PEAK: FareRule(
        base_fee=Decimal("30000"),
        per_km=Decimal("27000"),
        per_minute=Decimal("700"),
        min_fare=Decimal("120000"),
    ),
}

# Giờ thường: 06:00 <= t < 21:00 (giờ Việt Nam), còn lại là giờ đêm.
NORMAL_BAND_START_HOUR = 6
NORMAL_BAND_END_HOUR = 21
