"""Maps Directions / Distance Matrix (SPEC 4.3, 7.2) — interface chuẩn + fallback Haversine cho MVP."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from app.core.geo import haversine_km

ROAD_DISTANCE_FACTOR = Decimal("1.30")
AVG_CITY_SPEED_KMH = Decimal("25")


@dataclass
class RouteResult:
    distance_km: Decimal
    duration_minutes: int
    polyline: str


class MapsProvider(ABC):
    @abstractmethod
    async def get_route(
        self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
    ) -> RouteResult: ...

    @abstractmethod
    async def distance_km(
        self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
    ) -> Decimal: ...


class HaversineMapsProvider(MapsProvider):
    """Fallback MVP: đường chim bay × hệ số đường bộ. polyline chỉ gồm 2 điểm đầu-cuối."""

    async def get_route(
        self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
    ) -> RouteResult:
        straight = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
        distance = (straight * ROAD_DISTANCE_FACTOR).quantize(Decimal("0.01"))
        minutes = max(int((distance / AVG_CITY_SPEED_KMH * Decimal("60")).to_integral_value()), 1)
        polyline = f"{origin_lat},{origin_lng};{dest_lat},{dest_lng}"
        return RouteResult(distance_km=distance, duration_minutes=minutes, polyline=polyline)

    async def distance_km(
        self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
    ) -> Decimal:
        return (haversine_km(origin_lat, origin_lng, dest_lat, dest_lng) * ROAD_DISTANCE_FACTOR).quantize(
            Decimal("0.01")
        )


class GoogleMapsProvider(MapsProvider):
    """TODO: tích hợp Google Directions + Distance Matrix khi có ngân sách (SPEC 4.3)."""

    async def get_route(self, *args, **kwargs) -> RouteResult:
        raise NotImplementedError("Chưa tích hợp Google Maps")

    async def distance_km(self, *args, **kwargs) -> Decimal:
        raise NotImplementedError("Chưa tích hợp Google Maps")


_provider: MapsProvider = HaversineMapsProvider()


def get_maps_provider() -> MapsProvider:
    return _provider


def set_maps_provider(provider: MapsProvider) -> None:
    global _provider
    _provider = provider
