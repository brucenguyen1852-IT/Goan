"""Matching Service — tìm tài xế online gần điểm đón nhất bằng PostGIS.

Giai đoạn MVP: vị trí tài xế realtime được lưu trong Redis (key: driver:location:{id})
để tránh ghi DB liên tục mỗi 3-5s. Bảng dưới minh hoạ cách query khi vị trí được
đồng bộ định kỳ vào PostgreSQL/PostGIS cho các báo cáo/lịch sử.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# Bán kính tìm kiếm mở rộng dần, đúng chiến lược trong tài liệu kiến trúc (mục 3.3)
SEARCH_RADII_KM = [3, 5, 8, 12]


@dataclass
class DriverCandidate:
    driver_id: str
    distance_km: float


def find_nearby_drivers(db: Session, pickup_lat: float, pickup_lng: float, limit: int = 5) -> list[DriverCandidate]:
    """Mở rộng bán kính tìm kiếm dần cho đến khi có đủ ứng viên tài xế `online_idle`.

    Lưu ý: câu SQL dùng ST_DWithin trên geography nên đơn vị là MÉT.
    Trong triển khai thật, vị trí tài xế nên lấy từ Redis GEO (GEOSEARCH) để có độ trễ
    thấp hơn nhiều so với query PostgreSQL — hàm này dùng cho fallback/báo cáo.
    """
    for radius_km in SEARCH_RADII_KM:
        rows = db.execute(
            text(
                """
                SELECT dp.id AS driver_id,
                       ST_Distance(
                           dp.last_known_location,
                           ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                       ) / 1000.0 AS distance_km
                FROM driver_profiles dp
                WHERE dp.online_status = 'online_idle'
                  AND ST_DWithin(
                        dp.last_known_location,
                        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                        :radius_m
                      )
                ORDER BY distance_km ASC
                LIMIT :limit
                """
            ),
            {"lat": pickup_lat, "lng": pickup_lng, "radius_m": radius_km * 1000, "limit": limit},
        ).fetchall()

        if rows:
            return [DriverCandidate(driver_id=str(r.driver_id), distance_km=round(r.distance_km, 2)) for r in rows]

    return []
