"""Unit test cho pricing_service — không cần DB thật vì dùng fallback defaults
khi không tìm thấy PricingRule (xem get_active_pricing_rule)."""

from datetime import datetime
from unittest.mock import MagicMock

from app.services.pricing_service import calculate_fare


def _fake_db_no_rules():
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return db


def test_fare_uses_night_rate_and_far_pickup_surcharge():
    db = _fake_db_no_rules()
    requested_at = datetime(2026, 8, 21, 23, 0)  # 23h -> giờ đêm

    fare = calculate_fare(db, distance_km=11, duration_min=40, requested_at=requested_at)

    assert fare.time_band == "night"
    assert fare.surcharge_far_pickup == 20_000  # >5km nên có phụ thu
    assert fare.total_fare >= fare.subtotal_before_min


def test_fare_respects_minimum_fare():
    db = _fake_db_no_rules()
    requested_at = datetime(2026, 8, 21, 10, 0)  # giờ thường

    fare = calculate_fare(db, distance_km=1, duration_min=5, requested_at=requested_at)

    assert fare.total_fare == 100_000  # mức tối thiểu giờ thường, vì quãng đường quá ngắn
