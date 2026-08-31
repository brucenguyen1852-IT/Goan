import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.database import get_db
from app.models.payment import Payment, PaymentGateway, PaymentMethod, PaymentStatus
from app.models.trip import Trip, TripStatus
from app.models.user import User
from app.schemas.trip import FareEstimateIn, FareEstimateOut, QrVerifyIn, TripCreateIn, TripOut
from app.services.pricing_service import calculate_fare

router = APIRouter(prefix="/trips", tags=["trips"])


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Ước lượng khoảng cách đường chim bay — dùng tạm cho demo.
    Production nên gọi Maps Directions API để có khoảng cách đường bộ thật."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


@router.post("/fare-estimate", response_model=FareEstimateOut)
def fare_estimate(payload: FareEstimateIn, db: Session = Depends(get_db)) -> FareEstimateOut:
    distance_km = round(_haversine_km(
        payload.pickup.lat, payload.pickup.lng, payload.dropoff.lat, payload.dropoff.lng
    ), 2)
    duration_min = max(5, round(distance_km * 3))  # ước lượng thô ~20km/h nội thành

    fare = calculate_fare(db, distance_km=distance_km, duration_min=duration_min, requested_at=datetime.now(timezone.utc))
    return FareEstimateOut(
        time_band=fare.time_band,
        distance_km=distance_km,
        duration_min=duration_min,
        base_fare=fare.base_fare,
        distance_fare=fare.distance_fare,
        time_fare=fare.time_fare,
        surcharge_far_pickup=fare.surcharge_far_pickup,
        total_fare_estimate=fare.total_fare,
    )


@router.post("", response_model=TripOut, status_code=201)
def create_trip(payload: TripCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TripOut:
    now = datetime.now(timezone.utc)
    distance_km = round(_haversine_km(
        payload.pickup.lat, payload.pickup.lng, payload.dropoff.lat, payload.dropoff.lng
    ), 2)
    duration_min = max(5, round(distance_km * 3))
    fare = calculate_fare(db, distance_km=distance_km, duration_min=duration_min, requested_at=now)

    trip = Trip(
        id=uuid.uuid4(),
        customer_id=user.id,
        status=TripStatus.MATCHING,
        time_band=fare.time_band,
        pickup_geo=from_shape(Point(payload.pickup.lng, payload.pickup.lat), srid=4326),
        dropoff_geo=from_shape(Point(payload.dropoff.lng, payload.dropoff.lat), srid=4326),
        pickup_address=payload.pickup_address,
        dropoff_address=payload.dropoff_address,
        distance_km=distance_km,
        duration_min=duration_min,
        base_fare=fare.base_fare,
        distance_fare=fare.distance_fare,
        time_fare=fare.time_fare,
        surcharge_far_pickup=fare.surcharge_far_pickup,
        total_fare=fare.total_fare,
        requested_at=now,
    )
    db.add(trip)
    db.flush()  # để có trip.id trước khi tạo payment

    payment = Payment(
        trip_id=trip.id,
        method=PaymentMethod.ONLINE if payload.payment_method == "online" else PaymentMethod.CASH,
        gateway=PaymentGateway.NONE,
        status=PaymentStatus.PENDING_AUTH if payload.payment_method == "online" else PaymentStatus.CASH_DECLARED,
        estimated_amount=fare.total_fare,
        idempotency_key=f"{trip.id}-1",
    )
    db.add(payment)
    db.commit()
    db.refresh(trip)

    # TODO: publish event 'trip.requested' vào queue để Matching Service tìm tài xế async
    # (xem app/services/matching_service.py)

    return TripOut.model_validate(trip)


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TripOut:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chuyến đi")
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/qr-verify", response_model=TripOut)
def qr_verify(
    trip_id: uuid.UUID, payload: QrVerifyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TripOut:
    """Bắt buộc quét QR gắn với tài xế trước khi chuyển IN_PROGRESS — chống 'đơn ma'
    theo đúng cơ chế mô tả trong tài liệu kiến trúc mục 3.3 / 4.2."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chuyến đi")
    if trip.status != TripStatus.DRIVER_ARRIVING:
        raise HTTPException(status_code=400, detail="Chuyến đi chưa ở trạng thái sẵn sàng quét QR")

    # TODO: verify payload.qr_token khớp với token đã sinh cho driver_id của chuyến này
    trip.status = TripStatus.QR_VERIFIED
    trip.qr_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trip)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/cancel", response_model=TripOut)
def cancel_trip(trip_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TripOut:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chuyến đi")
    if trip.status in (TripStatus.COMPLETED, TripStatus.IN_PROGRESS):
        raise HTTPException(status_code=400, detail="Không thể hủy chuyến đã bắt đầu/hoàn thành")

    trip.status = TripStatus.CANCELLED_BY_CUSTOMER
    trip.cancel_reason = "Khách hàng hủy chuyến"
    db.commit()
    db.refresh(trip)
    return TripOut.model_validate(trip)
