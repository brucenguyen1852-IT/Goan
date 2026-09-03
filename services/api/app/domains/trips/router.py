import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.deps import (
    get_current_admin,
    get_current_driver,
    get_current_rider,
    get_current_user,
    get_redis,
)
from app.domains.matching import service as matching_service
from app.domains.trips import events as trip_events
from app.domains.trips import repository as trips_repo
from app.domains.trips import service as trips_service
from app.domains.trips.schemas import (
    ArrivedRequest,
    AssignDriverRequest,
    CancelTripRequest,
    CompleteTripRequest,
    CompleteTripResponse,
    GpsPing,
    GpsPointOut,
    RateTripRequest,
    RateTripResponse,
    TripCreate,
    TripCreateResponse,
    TripEventOut,
    TripOut,
    TripRatingOut,
    VerifyQrRequest,
)
from app.domains.users.models import User

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    payload: TripCreate,
    rider: User = Depends(get_current_rider),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TripCreateResponse:
    trip, estimate = await trips_service.create_trip(db, rider, payload)
    await matching_service.start_matching(db, redis, trip)
    return TripCreateResponse(trip=TripOut.model_validate(trip), estimate=estimate)


@router.get("", response_model=list[TripOut])
async def list_my_trips(
    limit: int = Query(20, ge=1, le=100),
    before: datetime | None = Query(
        None, description="Chỉ lấy chuyến đặt trước mốc này (phân trang)"
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TripOut]:
    """Lịch sử chuyến của chính người gọi — khách thấy chuyến mình đặt, tài xế thấy chuyến mình chạy."""
    trips = await trips_repo.list_trips_for_user(db, user.id, limit=limit, before=before)
    return [TripOut.model_validate(t) for t in trips]


@router.get("/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/cancel", response_model=TripOut)
async def cancel_trip(
    trip_id: uuid.UUID,
    payload: CancelTripRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    trip = await trips_service.cancel_trip(db, trip, user, payload.reason)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/verify-qr", response_model=TripOut)
async def verify_qr(
    trip_id: uuid.UUID,
    payload: VerifyQrRequest,
    rider: User = Depends(get_current_rider),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    """Rider quét QR tài xế -> qr_verified -> in_progress (SPEC 7.1)."""
    trip = await trips_service.get_trip_for_user(db, trip_id, rider)
    trip = await trips_service.verify_qr(db, trip, rider, payload.qr_token)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/complete", response_model=CompleteTripResponse)
async def complete_trip(
    trip_id: uuid.UUID,
    payload: CompleteTripRequest,
    driver: User = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
) -> CompleteTripResponse:
    trip = await trips_service.get_trip_for_user(db, trip_id, driver)
    result = await trips_service.complete_trip(
        db,
        trip,
        driver,
        lat=payload.lat,
        lng=payload.lng,
        idempotency_key=payload.idempotency_key,
    )
    return CompleteTripResponse(
        trip=TripOut.model_validate(result.trip),
        fare=result.fare,
        driver_actual_payout=result.driver_actual_payout,
        escrow_deducted=result.escrow_deducted,
        route_deviation_detected=result.route_deviation_detected,
    )


@router.get("/{trip_id}/gps-history", response_model=list[GpsPointOut])
async def gps_history(
    trip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GpsPointOut]:
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    points = await trips_repo.list_gps_logs(db, trip.id)
    return [GpsPointOut.model_validate(p) for p in points]


@router.post("/{trip_id}/gps-ping", status_code=status.HTTP_204_NO_CONTENT)
async def gps_ping(
    trip_id: uuid.UUID,
    payload: GpsPing,
    driver: User = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
) -> None:
    trip = await trips_service.get_trip_for_user(db, trip_id, driver)
    await trips_service.record_gps_ping(
        db, trip, driver, payload.lat, payload.lng, payload.recorded_at
    )


# --- Vòng đời chuyến: các bước còn thiếu ---------------------------------


@router.post("/{trip_id}/arrived", response_model=TripOut)
async def driver_arrived(
    trip_id: uuid.UUID,
    payload: ArrivedRequest,
    driver: User = Depends(get_current_driver),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    """Tài xế báo đã tới điểm đón.

    Không có mốc này thì app khách hiển thị "tài xế đã đến" ngay lúc tài xế mới nhận chuyến
    và còn cách vài km.
    """
    trip = await trips_service.get_trip_for_user(db, trip_id, driver)
    trip = await trips_service.mark_driver_arrived(db, trip, driver, payload.lat, payload.lng)
    return TripOut.model_validate(trip)


@router.post("/{trip_id}/rate", response_model=RateTripResponse)
async def rate_trip(
    trip_id: uuid.UUID,
    payload: RateTripRequest,
    rider: User = Depends(get_current_rider),
    db: AsyncSession = Depends(get_db),
) -> RateTripResponse:
    """Khách đánh giá tài xế — bước cuối vòng đời chuyến, đưa chuyến sang trạng thái `rated`."""
    trip = await trips_service.get_trip_for_user(db, trip_id, rider)
    rating, profile = await trips_service.rate_trip(db, trip, rider, payload.stars, payload.comment)
    _, total = await trips_repo.driver_rating_stats(db, rating.driver_id)
    return RateTripResponse(
        rating=TripRatingOut.model_validate(rating),
        driver_rating_avg=profile.rating_avg,
        driver_total_ratings=total,
    )


@router.post("/{trip_id}/retry-matching", response_model=TripOut)
async def retry_matching(
    trip_id: uuid.UUID,
    rider: User = Depends(get_current_rider),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TripOut:
    """Tìm lại tài xế cho chuyến `no_driver_found`, giữ nguyên chuyến cũ.

    Đặt lại từ đầu sẽ tạo chuyến mới và mất liên kết với đối tác (QR nhà hàng) của lần đặt đầu.
    """
    trip = await trips_service.get_trip_for_user(db, trip_id, rider)
    trip = await matching_service.retry_matching(db, redis, trip, rider.id)
    return TripOut.model_validate(trip)


@router.get("/{trip_id}/events", response_model=list[TripEventOut])
async def trip_timeline(
    trip_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TripEventOut]:
    """Dòng thời gian đầy đủ của chuyến — thứ CSKH mở ra khi khách khiếu nại."""
    trip = await trips_service.get_trip_for_user(db, trip_id, user)
    rows = await trip_events.list_for_trip(db, trip.id)
    return [TripEventOut.model_validate(r) for r in rows]


# --- Điều phối viên (Live Ops) -------------------------------------------

ops_router = APIRouter(prefix="/ops/trips", tags=["ops"])


@ops_router.post("/{trip_id}/assign-driver", response_model=TripOut)
async def ops_assign_driver(
    trip_id: uuid.UUID,
    payload: AssignDriverRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TripOut:
    """Gán tài xế thủ công khi matching tự động không ra kết quả.

    Bỏ qua bước gửi offer nhưng vẫn đi đúng state machine, và ghi rõ người thao tác cùng
    lý do vào dòng thời gian của chuyến.
    """
    trip = await trips_repo.get_trip(db, trip_id)
    if trip is None:
        raise NotFoundError("Không tìm thấy chuyến")
    trip = await matching_service.assign_driver_manually(
        db, redis, trip, payload.driver_id, admin.id, payload.reason
    )
    return TripOut.model_validate(trip)


@ops_router.post("/{trip_id}/cancel", response_model=TripOut)
async def ops_cancel_trip(
    trip_id: uuid.UUID,
    payload: CancelTripRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> TripOut:
    """CSKH huỷ hộ khi khách gọi tổng đài hoặc tài xế mất liên lạc.

    Bắt buộc có lý do. Không tính phí huỷ cho khách — nếu tính thì mọi cuộc gọi tổng đài
    đều thành một khoản tranh chấp.
    """
    trip = await trips_repo.get_trip(db, trip_id)
    if trip is None:
        raise NotFoundError("Không tìm thấy chuyến")
    trip = await trips_service.cancel_trip(db, trip, admin, payload.reason, on_behalf_of_ops=True)
    return TripOut.model_validate(trip)
