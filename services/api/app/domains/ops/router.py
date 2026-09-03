"""Console vận hành: bản đồ đội xe, duyệt hồ sơ tài xế, tra cứu chuyến (P1-09, P1-10, P1-11).

Router này chỉ phục vụ Console. Cùng một nghiệp vụ có thể được gọi từ app tài xế và từ đây,
nhưng khác nhau ở lớp quyền và ở chỗ mọi thao tác đều để lại dấu vết kèm lý do.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    SETTLED_TRIP_STATUSES,
    DriverApprovalStatus,
    OnlineStatus,
    TripStatus,
    UserStatus,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pii import mask_name, mask_phone
from app.core.security import decrypt_national_id, mask_national_id
from app.database import get_db
from app.deps import require_permission
from app.domains.iam.models import StaffUser
from app.domains.notifications import service as notifications
from app.domains.ops.schemas import (
    ApproveRequest,
    DecisionRequest,
    FleetDriverOut,
    FleetSnapshot,
    GpsPointOut,
    OpsDriverOut,
    OpsTripOut,
    OpsTripPage,
)
from app.domains.trips.models import Trip, TripGpsLog
from app.domains.users.models import DriverProfile, User
from app.websocket.events import ServerEvent

router = APIRouter(prefix="/ops", tags=["ops-fleet"])

ACTIVE_TRIP_STATUSES = (
    TripStatus.MATCHED,
    TripStatus.DRIVER_ARRIVING,
    TripStatus.QR_VERIFIED,
    TripStatus.IN_PROGRESS,
)


# --- P1-09: bản đồ đội xe -------------------------------------------------------------


@router.get("/fleet", response_model=FleetSnapshot)
async def fleet_snapshot(
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("ops:fleet:read")),
) -> FleetSnapshot:
    """Ảnh chụp toàn đội tại một thời điểm: ai đang online, ai đang chạy chuyến nào.

    Console gọi lại mỗi vài giây. Không kèm PII — bản đồ không cần số điện thoại; muốn liên hệ
    thì đi qua /ops/users/{id}/reveal-pii và để lại lý do.
    """
    stmt = select(DriverProfile).where(DriverProfile.online_status != OnlineStatus.OFFLINE)
    profiles = list((await db.execute(stmt)).scalars().all())

    active_trips = list(
        (await db.execute(select(Trip).where(Trip.status.in_(ACTIVE_TRIP_STATUSES))))
        .scalars()
        .all()
    )
    trip_by_driver = {t.driver_id: t.id for t in active_trips if t.driver_id}

    drivers = [
        FleetDriverOut(
            driver_id=p.user_id,
            full_name_masked=mask_name(p.user.full_name if p.user else None),
            online_status=p.online_status,
            lat=p.current_lat,
            lng=p.current_lng,
            rating_avg=p.rating_avg,
            total_trips=p.total_trips,
            current_trip_id=trip_by_driver.get(p.user_id),
        )
        for p in profiles
    ]
    return FleetSnapshot(
        taken_at=datetime.now(timezone.utc),
        drivers_online=sum(1 for p in profiles if p.online_status is OnlineStatus.ONLINE),
        drivers_on_trip=sum(1 for p in profiles if p.online_status is OnlineStatus.ON_TRIP),
        trips_active=len(active_trips),
        drivers=drivers,
    )


# --- P1-10: vận hành tài xế -----------------------------------------------------------


async def _get_profile(db: AsyncSession, driver_user_id: uuid.UUID) -> DriverProfile:
    stmt = select(DriverProfile).where(DriverProfile.user_id == driver_user_id)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if profile is None:
        raise NotFoundError("Không tìm thấy hồ sơ tài xế")
    return profile


def _driver_out(profile: DriverProfile) -> OpsDriverOut:
    user = profile.user
    return OpsDriverOut(
        driver_id=profile.user_id,
        user_id=profile.user_id,
        full_name=user.full_name,
        phone_masked=mask_phone(user.phone),
        national_id_masked=mask_national_id(
            decrypt_national_id(user.national_id_number) if user.national_id_number else None
        ),
        national_id_verified=user.national_id_verified,
        license_number=profile.license_number,
        approval_status=profile.approval_status,
        approval_note=profile.approval_note,
        approved_at=profile.approved_at,
        account_status=user.status,
        online_status=profile.online_status,
        rating_avg=profile.rating_avg,
        total_trips=profile.total_trips,
        fraud_strikes=profile.fraud_strikes,
        escrow_balance=profile.escrow_balance,
    )


@router.get("/drivers", response_model=list[OpsDriverOut])
async def list_drivers(
    approval_status: DriverApprovalStatus | None = Query(default=None),
    account_status: UserStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("driver:profile:read")),
) -> list[OpsDriverOut]:
    stmt = select(DriverProfile).order_by(DriverProfile.created_at.desc()).limit(limit)
    if approval_status:
        stmt = stmt.where(DriverProfile.approval_status == approval_status)
    if account_status:
        stmt = stmt.join(User, User.id == DriverProfile.user_id).where(
            User.status == account_status
        )
    return [_driver_out(p) for p in (await db.execute(stmt)).scalars().all()]


@router.get("/drivers/{driver_id}", response_model=OpsDriverOut)
async def get_driver(
    driver_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("driver:profile:read")),
) -> OpsDriverOut:
    return _driver_out(await _get_profile(db, driver_id))


@router.post("/drivers/{driver_id}/approve", response_model=OpsDriverOut)
async def approve_driver(
    driver_id: uuid.UUID,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("driver:profile:approve")),
) -> OpsDriverOut:
    profile = await _get_profile(db, driver_id)
    if profile.approval_status is DriverApprovalStatus.APPROVED:
        raise ConflictError("Hồ sơ đã được duyệt trước đó")
    profile.approval_status = DriverApprovalStatus.APPROVED
    profile.approval_note = body.note
    profile.approved_at = datetime.now(timezone.utc)
    profile.approved_by = staff.id
    await db.commit()
    await db.refresh(profile)
    await notifications.notify_user(
        profile.user_id, ServerEvent.SYSTEM_NOTICE, message="Hồ sơ của bạn đã được duyệt"
    )
    return _driver_out(profile)


@router.post("/drivers/{driver_id}/reject", response_model=OpsDriverOut)
async def reject_driver(
    driver_id: uuid.UUID,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    staff: StaffUser = Depends(require_permission("driver:profile:approve")),
) -> OpsDriverOut:
    """Từ chối phải có lý do, và tài xế phải biết lý do — nếu không họ nộp lại y hệt."""
    profile = await _get_profile(db, driver_id)
    profile.approval_status = DriverApprovalStatus.REJECTED
    profile.approval_note = body.reason
    profile.approved_at = None
    profile.approved_by = staff.id
    await db.commit()
    await db.refresh(profile)
    await notifications.notify_user(
        profile.user_id,
        ServerEvent.SYSTEM_NOTICE,
        message=f"Hồ sơ chưa được duyệt: {body.reason}",
    )
    return _driver_out(profile)


@router.post("/drivers/{driver_id}/lock", response_model=OpsDriverOut)
async def lock_driver(
    driver_id: uuid.UUID,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("driver:account:lock")),
) -> OpsDriverOut:
    profile = await _get_profile(db, driver_id)
    user = profile.user
    user.status = UserStatus.SUSPENDED
    profile.online_status = OnlineStatus.OFFLINE
    profile.active_qr_token = None  # khoá mà QR còn sống thì vẫn nhận được chuyến
    await db.commit()
    await db.refresh(profile)
    await notifications.notify_user(
        profile.user_id,
        ServerEvent.SYSTEM_NOTICE,
        message=f"Tài khoản tạm khoá: {body.reason}",
    )
    return _driver_out(profile)


@router.post("/drivers/{driver_id}/unlock", response_model=OpsDriverOut)
async def unlock_driver(
    driver_id: uuid.UUID,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("driver:account:lock")),
) -> OpsDriverOut:
    profile = await _get_profile(db, driver_id)
    profile.user.status = UserStatus.ACTIVE
    await db.commit()
    await db.refresh(profile)
    await notifications.notify_user(
        profile.user_id, ServerEvent.SYSTEM_NOTICE, message="Tài khoản đã được mở lại"
    )
    return _driver_out(profile)


# --- P1-11: tra cứu chuyến ------------------------------------------------------------


@router.get("/trips", response_model=OpsTripPage)
async def list_trips(
    status: TripStatus | None = Query(default=None),
    driver_id: uuid.UUID | None = Query(default=None),
    rider_id: uuid.UUID | None = Query(default=None),
    settled_only: bool = Query(default=False, description="Chỉ chuyến đã chốt tiền"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("trip:trip:read_all")),
) -> OpsTripPage:
    """Phân trang bằng con trỏ thời gian: bảng chuyến chỉ lớn dần, OFFSET sẽ chậm dần."""
    stmt = select(Trip).order_by(Trip.created_at.desc()).limit(limit + 1)
    if status:
        stmt = stmt.where(Trip.status == status)
    if settled_only:
        stmt = stmt.where(Trip.status.in_(SETTLED_TRIP_STATUSES))
    if driver_id:
        stmt = stmt.where(Trip.driver_id == driver_id)
    if rider_id:
        stmt = stmt.where(Trip.rider_id == rider_id)
    if since:
        stmt = stmt.where(Trip.created_at >= since)
    if until:
        stmt = stmt.where(Trip.created_at <= until)
    if cursor:
        stmt = stmt.where(Trip.created_at < cursor)

    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1].created_at
        next_cursor = (
            (last if last.tzinfo else last.replace(tzinfo=timezone.utc))
            .isoformat()
            .replace("+00:00", "Z")
        )
    return OpsTripPage(items=[OpsTripOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.get("/trips/{trip_id}/detail", response_model=OpsTripOut)
async def get_trip(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("trip:trip:read_all")),
) -> OpsTripOut:
    trip = await db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("Không tìm thấy chuyến")
    return OpsTripOut.model_validate(trip)


@router.get("/trips/{trip_id}/gps", response_model=list[GpsPointOut])
async def trip_gps(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("trip:trip:read_all")),
) -> list[GpsPointOut]:
    """Tua lại lộ trình: cần cho tranh chấp cước và cho điều tra chạy vòng."""
    stmt = (
        select(TripGpsLog)
        .where(TripGpsLog.trip_id == trip_id)
        .order_by(TripGpsLog.recorded_at.asc())
    )
    return [GpsPointOut.model_validate(p) for p in (await db.execute(stmt)).scalars().all()]


@router.get("/stats/today")
async def stats_today(
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("trip:trip:read_all")),
) -> dict:
    """Vài con số cho đầu trang Console. Không thay thế báo cáo phân tích (P5)."""
    total = await db.scalar(select(func.count()).select_from(Trip))
    settled = await db.scalar(
        select(func.count()).select_from(Trip).where(Trip.status.in_(SETTLED_TRIP_STATUSES))
    )
    active = await db.scalar(
        select(func.count()).select_from(Trip).where(Trip.status.in_(ACTIVE_TRIP_STATUSES))
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(Trip.platform_commission), 0)).where(
            Trip.status.in_(SETTLED_TRIP_STATUSES)
        )
    )
    return {
        "trips_total": total or 0,
        "trips_settled": settled or 0,
        "trips_active": active or 0,
        "platform_commission_total": str(revenue or 0),
    }
