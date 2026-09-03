"""Tính khoảng cách địa lý. MVP dùng Haversine (SPEC 4.3 cho phép fallback Haversine)."""

from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> Decimal:
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    km = 2 * EARTH_RADIUS_KM * asin(sqrt(a))
    return Decimal(str(round(km, 2)))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return float(haversine_km(lat1, lng1, lat2, lng2)) * 1000
