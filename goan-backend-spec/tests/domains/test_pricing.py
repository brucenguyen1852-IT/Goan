"""Unit test pricing_service (SPEC 4.4 yêu cầu bắt buộc).

Bao phủ: giờ thường/đêm/cao điểm, có/không phụ thu đón xa, cước dưới mức tối thiểu.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.core.constants import TimeBand
from app.domains.pricing.constants import DEFAULT_FARE_RULES
from app.domains.pricing.service import (
    calculate_fare,
    calculate_pickup_surcharge,
    resolve_time_band,
)


def _fare(distance: str, minutes: int, band: TimeBand, pickup_km: str | None = None):
    return calculate_fare(
        distance_km=Decimal(distance),
        duration_minutes=minutes,
        time_band=band,
        driver_to_pickup_distance_km=Decimal(pickup_km) if pickup_km else None,
    )


# --- Khung giờ ------------------------------------------------------------


def test_time_band_normal_hours_in_vietnam_time():
    # 08:00 giờ VN = 01:00 UTC
    assert resolve_time_band(datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)) is TimeBand.NORMAL


def test_time_band_night_after_21h_vietnam_time():
    # 22:00 giờ VN = 15:00 UTC
    assert resolve_time_band(datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)) is TimeBand.NIGHT


def test_time_band_night_before_6h_vietnam_time():
    # 04:00 giờ VN = 21:00 UTC hôm trước
    assert resolve_time_band(datetime(2026, 8, 30, 21, 0, tzinfo=timezone.utc)) is TimeBand.NIGHT


def test_time_band_peak_override():
    at = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
    assert resolve_time_band(at, is_peak=True) is TimeBand.PEAK


# --- Biểu giá đúng theo deck ---------------------------------------------


def test_default_rules_match_spec_table():
    normal, night, peak = (
        DEFAULT_FARE_RULES[TimeBand.NORMAL],
        DEFAULT_FARE_RULES[TimeBand.NIGHT],
        DEFAULT_FARE_RULES[TimeBand.PEAK],
    )
    assert (normal.base_fee, normal.per_km, normal.per_minute, normal.min_fare) == (
        Decimal("30000"),
        Decimal("20000"),
        Decimal("500"),
        Decimal("100000"),
    )
    assert (night.per_km, night.per_minute, night.min_fare) == (
        Decimal("24000"),
        Decimal("600"),
        Decimal("110000"),
    )
    assert (peak.per_km, peak.per_minute, peak.min_fare) == (
        Decimal("27000"),
        Decimal("700"),
        Decimal("120000"),
    )


def test_normal_band_fare_breakdown():
    fare = _fare("10", 30, TimeBand.NORMAL)
    assert fare.base_fee == Decimal("30000")
    assert fare.distance_fee == Decimal("200000")
    assert fare.time_fee == Decimal("15000")
    assert fare.subtotal == Decimal("245000")
    assert fare.final_fare == Decimal("245000")


def test_night_band_matches_deck_reference_example():
    """Ví dụ tham chiếu trong deck: đêm, 11km/40 phút -> ~318.000đ, tài xế ~58%."""
    fare = _fare("11", 40, TimeBand.NIGHT)
    assert fare.final_fare == Decimal("318000")
    assert fare.driver_payout == Decimal("184440")  # 58%
    assert fare.platform_commission == Decimal("120840")  # take-rate 38%


def test_peak_band_uses_peak_rates():
    fare = _fare("5", 20, TimeBand.PEAK)
    assert fare.distance_fee == Decimal("135000")
    assert fare.time_fee == Decimal("14000")
    assert fare.final_fare == Decimal("179000")


# --- Cước tối thiểu -------------------------------------------------------


def test_below_minimum_fare_is_raised_to_minimum_normal():
    fare = _fare("1", 5, TimeBand.NORMAL)
    assert fare.subtotal == Decimal("52500")
    assert fare.final_fare == Decimal("100000")


def test_below_minimum_fare_night_and_peak():
    assert _fare("0.5", 2, TimeBand.NIGHT).final_fare == Decimal("110000")
    assert _fare("0.5", 2, TimeBand.PEAK).final_fare == Decimal("120000")


# --- Phụ thu đón xa -------------------------------------------------------


def test_no_pickup_surcharge_within_5km():
    assert calculate_pickup_surcharge(Decimal("5")) == Decimal("0")
    assert calculate_pickup_surcharge(Decimal("4.99")) == Decimal("0")
    assert calculate_pickup_surcharge(None) == Decimal("0")
    assert _fare("10", 30, TimeBand.NORMAL, "3").pickup_surcharge == Decimal("0")


def test_pickup_surcharge_beyond_5km_goes_fully_to_driver():
    fare = _fare("10", 30, TimeBand.NORMAL, "7.5")
    assert fare.pickup_surcharge == Decimal("20000")
    assert fare.subtotal == Decimal("265000")
    assert fare.final_fare == Decimal("265000")

    fare_ex_surcharge = fare.final_fare - fare.pickup_surcharge
    # 100% phụ thu về tài xế, không bị chia take-rate.
    assert fare.driver_payout == (fare_ex_surcharge * Decimal("0.58")).quantize(
        Decimal("1")
    ) + Decimal("20000")
    assert fare.platform_commission == (fare_ex_surcharge * Decimal("0.38")).quantize(Decimal("1"))


def test_pickup_surcharge_applies_after_minimum_fare():
    """Cước thấp hơn mức tối thiểu nhưng có phụ thu: min fare vẫn áp trên tổng đã gồm phụ thu."""
    fare = _fare("1", 5, TimeBand.NORMAL, "8")
    assert fare.pickup_surcharge == Decimal("20000")
    assert fare.subtotal == Decimal("72500")
    assert fare.final_fare == Decimal("100000")


# --- Phân bổ doanh thu ----------------------------------------------------


def test_revenue_split_and_deductions_are_decimal_vnd():
    fare = _fare("10", 30, TimeBand.NORMAL)
    assert fare.driver_payout == Decimal("142100")
    assert fare.platform_commission == Decimal("93100")
    assert fare.insurance_fee == Decimal("14700")  # 6% final_fare, trừ trong phần nền tảng
    assert fare.payment_gateway_fee == Decimal("4900")  # 2% final_fare
    for value in (
        fare.base_fee,
        fare.distance_fee,
        fare.time_fee,
        fare.final_fare,
        fare.driver_payout,
        fare.platform_commission,
    ):
        assert isinstance(value, Decimal)
        assert value == value.to_integral_value()  # VNĐ không có phần thập phân


def test_driver_and_platform_share_do_not_exceed_fare():
    fare = _fare("11", 40, TimeBand.NIGHT)
    assert fare.driver_payout + fare.platform_commission <= fare.final_fare
