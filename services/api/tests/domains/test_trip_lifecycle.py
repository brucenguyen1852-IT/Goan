"""QA-LIFE — vòng đời chuyến đầy đủ: dấu vết, mốc tài xế tới, đánh giá, tìm lại tài xế,
gán thủ công, và phí huỷ thực sự tới tay tài xế.

Ánh xạ PRD: PRD-TRIP-07…12 trong docs/QA/TRACEABILITY.md.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.constants import (
    OnlineStatus,
    TripActorType,
    TripEventType,
    TripStatus,
    UserRole,
)
from app.core.exceptions import (
    ConflictError,
    InvalidTransitionError,
    PermissionDeniedError,
)
from app.domains.matching import service as matching_service
from app.domains.payments.models import DriverWallet
from app.domains.trips import events as trip_events
from app.domains.trips import repository as trips_repo
from app.domains.trips import service as trips_service
from app.domains.trips.models import Trip, TripEvent
from app.domains.users.models import User
from tests.conftest import create_driver, create_rider, create_trip

pytestmark = [pytest.mark.integration, pytest.mark.prd]


async def _completed_trip(db, *, rider=None, driver=None):
    rider = rider or await create_rider(db)
    if driver is None:
        driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.COMPLETED)
    trip.final_fare = Decimal("150000")
    trip.driver_payout = Decimal("87000")
    await db.commit()
    return rider, driver, trip


# --- Dấu vết vòng đời chuyến ---------------------------------------------


async def test_moi_chuyen_trang_thai_deu_ghi_dau_vet(db, fake_redis):
    """QA-LIFE-01: đổi trạng thái mà không để lại dấu vết là điều không được xảy ra.

    Khi khách khiếu nại "sao chuyến của tôi bị huỷ", CSKH cần dòng thời gian đầy đủ. Nếu
    chỉ có audit_logs (ghi theo request HTTP) thì mọi chuyển trạng thái do hệ thống tự làm —
    hết hạn matching, job nền — đều biến mất.
    """
    rider = await create_rider(db)
    driver, profile = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    await trips_service.verify_qr(db, trip, rider, profile.active_qr_token)

    events = await trip_events.list_for_trip(db, trip.id)
    kinds = [e.event_type for e in events]
    assert TripEventType.QR_VERIFIED in kinds
    assert events[-1].to_status is TripStatus.IN_PROGRESS
    assert events[-1].actor_type is TripActorType.RIDER
    assert events[-1].actor_id == rider.id


async def test_dau_vet_ghi_ca_trang_thai_truoc_va_sau(db):
    """QA-LIFE-02: chỉ ghi "đổi sang X" là chưa đủ để dựng lại chuyện gì đã xảy ra."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    await trips_service.cancel_trip(db, trip, rider, "Đổi ý")

    event = (await trip_events.list_for_trip(db, trip.id))[-1]
    assert event.from_status is TripStatus.DRIVER_ARRIVING
    assert event.to_status is TripStatus.CANCELLED_BY_RIDER
    assert event.payload["reason"] == "Đổi ý"


async def test_dau_vet_bi_rollback_cung_transaction(db):
    """QA-LIFE-03: dấu vết nói chuyến đã hoàn thành trong khi transaction đã rollback còn
    tệ hơn là không có dấu vết nào."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.MATCHED)

    with pytest.raises(InvalidTransitionError):
        # matched -> completed là bước nhảy không hợp lệ; hàm phải ném lỗi và không để lại gì
        await trips_service._set_status(
            db, trip, TripStatus.COMPLETED, event=TripEventType.COMPLETED
        )
    await db.rollback()

    assert await trip_events.list_for_trip(db, trip.id) == []


# --- Mốc tài xế đã tới điểm đón ------------------------------------------


async def test_tai_xe_bao_da_toi(db):
    """QA-LIFE-04: trước đây không có mốc này nên app khách hiện "tài xế đã đến" ngay lúc
    tài xế mới bấm nhận chuyến và còn cách vài km."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)
    assert trip.driver_arrived_at is None

    await trips_service.mark_driver_arrived(db, trip, driver, 10.7769, 106.7009)

    assert trip.driver_arrived_at is not None
    assert trip.status is TripStatus.DRIVER_ARRIVING, "Báo đã tới KHÔNG đổi trạng thái chuyến"
    event = (await trip_events.list_for_trip(db, trip.id))[-1]
    assert event.event_type is TripEventType.DRIVER_ARRIVED
    assert event.payload["distance_to_pickup_m"] < 200, "Toạ độ báo tới phải sát điểm đón"


async def test_bao_da_toi_ghi_khoang_cach_de_doi_chieu(db):
    """QA-LIFE-05: báo "đã tới" khi còn cách 5km là dấu hiệu bất thường, phải lưu lại được."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    await trips_service.mark_driver_arrived(db, trip, driver, 10.8300, 106.7009)

    event = (await trip_events.list_for_trip(db, trip.id))[-1]
    assert event.payload["distance_to_pickup_m"] > 5000


async def test_bao_da_toi_hai_lan_khong_doi_gi(db):
    """QA-LIFE-06: mạng chập chờn, tài xế bấm hai lần."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    await trips_service.mark_driver_arrived(db, trip, driver, 10.7769, 106.7009)
    first = trip.driver_arrived_at
    await trips_service.mark_driver_arrived(db, trip, driver, 10.7769, 106.7009)

    assert trip.driver_arrived_at == first
    kinds = [e.event_type for e in await trip_events.list_for_trip(db, trip.id)]
    assert kinds.count(TripEventType.DRIVER_ARRIVED) == 1


async def test_tai_xe_khac_khong_bao_ho_duoc(db):
    """QA-LIFE-07: phân quyền theo chuyến, không chỉ theo vai trò."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    other, _ = await create_driver(db, phone="0900009999")
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    with pytest.raises(PermissionDeniedError):
        await trips_service.mark_driver_arrived(db, trip, other, 10.7769, 106.7009)


# --- Đánh giá sau chuyến --------------------------------------------------


async def test_danh_gia_dua_chuyen_sang_trang_thai_cuoi(db):
    """QA-LIFE-08: `rated` là trạng thái cuối theo deck mục 3.3, trước đây chưa tồn tại."""
    rider, driver, trip = await _completed_trip(db)

    rating, profile = await trips_service.rate_trip(db, trip, rider, 5, "Tài xế lái êm")

    assert trip.status is TripStatus.RATED
    assert trip.rated_at is not None
    assert rating.stars == 5
    assert profile.rating_avg == Decimal("5.00")


async def test_rating_avg_tinh_lai_tu_toan_bo_danh_gia(db):
    """QA-LIFE-09: cộng dồn tăng dần thì mọi lần sửa/xoá đánh giá về sau đều làm lệch
    vĩnh viễn và không đối chiếu lại được."""
    driver, _ = await create_driver(db)
    for i, stars in enumerate([5, 3, 4]):
        rider = await create_rider(db, phone=f"090100{i:04d}")
        _, _, trip = await _completed_trip(db, rider=rider, driver=driver)
        await trips_service.rate_trip(db, trip, rider, stars, None)

    avg, total = await trips_repo.driver_rating_stats(db, driver.id)
    assert total == 3
    assert avg == Decimal("4.00")


async def test_khong_danh_gia_duoc_hai_lan(db):
    """QA-LIFE-10: một chuyến một đánh giá — nếu không thì tài xế bị dìm sao vô hạn."""
    rider, _, trip = await _completed_trip(db)
    await trips_service.rate_trip(db, trip, rider, 5, None)

    with pytest.raises(ConflictError):
        await trips_service.rate_trip(db, trip, rider, 1, "Đổi ý")


async def test_khong_danh_gia_chuyen_chua_hoan_thanh(db):
    """QA-LIFE-11: đánh giá khi chuyến đang chạy là vô nghĩa."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.IN_PROGRESS)

    with pytest.raises(ConflictError):
        await trips_service.rate_trip(db, trip, rider, 5, None)


async def test_nguoi_khac_khong_danh_gia_ho_duoc(db):
    """QA-LIFE-12: chỉ khách của chuyến mới được đánh giá."""
    rider, _, trip = await _completed_trip(db)
    ke_khac = await create_rider(db, phone="0901009999")

    with pytest.raises(PermissionDeniedError):
        await trips_service.rate_trip(db, trip, ke_khac, 1, None)


@pytest.mark.parametrize("stars", [0, 6, -1])
async def test_so_sao_ngoai_khoang_bi_chan_o_schema(stars):
    """QA-LIFE-13: chặn ở schema, không để tầng nghiệp vụ phải tự lo."""
    from pydantic import ValidationError

    from app.domains.trips.schemas import RateTripRequest

    with pytest.raises(ValidationError):
        RateTripRequest(stars=stars)


# --- Phí huỷ phải tới tay tài xế -----------------------------------------


@pytest.mark.money
async def test_phi_huy_muon_duoc_cong_vao_vi_tai_xe(db):
    """QA-LIFE-14: trước đây phí huỷ chỉ được ghi vào bảng trips và KHÔNG có bút toán nào —
    tài xế chạy tới điểm đón rồi bị huỷ là mất công trắng."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)
    trip.matched_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.CANCELLATION_GRACE_MINUTES + 5
    )
    await db.commit()

    await trips_service.cancel_trip(db, trip, rider, "Đổi ý")

    assert trip.cancellation_fee == settings.CANCELLATION_FEE
    wallet = await db.get(DriverWallet, driver.id)
    assert wallet is not None, "Phải có bút toán vào ví tài xế"
    assert wallet.pending_balance == settings.CANCELLATION_FEE


@pytest.mark.money
async def test_huy_som_khong_tinh_phi(db):
    """QA-LIFE-15: huỷ trong thời gian ân hạn thì không ai bị mất gì."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.MATCHED)
    trip.matched_at = datetime.now(timezone.utc)
    await db.commit()

    await trips_service.cancel_trip(db, trip, rider, None)

    assert trip.cancellation_fee == Decimal("0")
    assert await db.get(DriverWallet, driver.id) is None


# --- Tìm lại tài xế -------------------------------------------------------


async def test_tim_lai_tai_xe_giu_nguyen_chuyen_cu(db, fake_redis):
    """QA-LIFE-16: đặt lại từ đầu sẽ tạo chuyến mới và mất liên kết với đối tác (QR nhà
    hàng) của lần đặt đầu."""
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, status=TripStatus.NO_DRIVER_FOUND)
    trip_id = trip.id
    await fake_redis.geoadd("driver_locations", [106.7009, 10.7769, str(driver.id)])

    await matching_service.retry_matching(db, fake_redis, trip, rider.id)

    assert trip.id == trip_id, "Phải là cùng một chuyến, không phải chuyến mới"
    assert trip.status is TripStatus.MATCHING
    kinds = [e.event_type for e in await trip_events.list_for_trip(db, trip.id)]
    assert TripEventType.MATCHING_RETRIED in kinds


async def test_khong_tim_lai_khi_chuyen_dang_chay(db, fake_redis):
    """QA-LIFE-17: chỉ tìm lại được từ đúng trạng thái no_driver_found."""
    rider = await create_rider(db)
    trip = await create_trip(db, rider, status=TripStatus.MATCHING)

    with pytest.raises(ConflictError):
        await matching_service.retry_matching(db, fake_redis, trip, rider.id)


# --- Điều phối viên gán tài xế thủ công ----------------------------------


async def test_dieu_phoi_gan_tai_xe_thu_cong(db, fake_redis):
    """QA-LIFE-18: khu vực thưa tài xế, khách gọi tổng đài — Live Ops phải gán được tay."""
    admin = User(phone="0900000000", full_name="Điều phối", role=UserRole.ADMIN)
    db.add(admin)
    rider = await create_rider(db)
    driver, profile = await create_driver(db)
    trip = await create_trip(db, rider, status=TripStatus.NO_DRIVER_FOUND)
    await db.commit()

    await matching_service.assign_driver_manually(
        db, fake_redis, trip, driver.id, admin.id, "Khách gọi tổng đài, khu vực thưa tài xế"
    )

    assert trip.driver_id == driver.id
    assert trip.status is TripStatus.DRIVER_ARRIVING
    assert profile.online_status is OnlineStatus.ON_TRIP
    event = [
        e
        for e in await trip_events.list_for_trip(db, trip.id)
        if e.event_type is TripEventType.DRIVER_ASSIGNED_MANUALLY
    ][0]
    assert event.actor_type is TripActorType.ADMIN
    assert event.actor_id == admin.id
    assert "tổng đài" in event.payload["reason"]


async def test_khong_gan_tai_xe_dang_ban(db, fake_redis):
    """QA-LIFE-19: gán tài xế đang chạy chuyến khác là tạo ra hai chuyến cùng một người."""
    admin = User(phone="0900000000", full_name="Điều phối", role=UserRole.ADMIN)
    db.add(admin)
    rider = await create_rider(db)
    driver, profile = await create_driver(db)
    profile.online_status = OnlineStatus.ON_TRIP
    trip = await create_trip(db, rider, status=TripStatus.NO_DRIVER_FOUND)
    await db.commit()

    with pytest.raises(ConflictError):
        await matching_service.assign_driver_manually(
            db, fake_redis, trip, driver.id, admin.id, "Thử gán tài xế đang bận"
        )


async def test_cskh_huy_ho_khong_tinh_phi_khach(db):
    """QA-LIFE-20: nếu tính phí khi CSKH huỷ hộ thì mọi cuộc gọi tổng đài đều thành một
    khoản tranh chấp."""
    admin = User(phone="0900000000", full_name="CSKH", role=UserRole.ADMIN)
    db.add(admin)
    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)
    trip.matched_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    await db.commit()

    await trips_service.cancel_trip(db, trip, admin, "Tài xế mất liên lạc", on_behalf_of_ops=True)

    assert trip.cancellation_fee == Decimal("0")
    event = (await trip_events.list_for_trip(db, trip.id))[-1]
    assert event.actor_type is TripActorType.ADMIN
    assert event.payload["on_behalf_of_ops"] is True


async def test_huy_ho_bat_buoc_co_ly_do(db):
    """QA-LIFE-21: thao tác thay mặt người khác mà không ghi lý do là không kiểm toán được."""
    from app.core.exceptions import AppError

    admin = User(phone="0900000000", full_name="CSKH", role=UserRole.ADMIN)
    db.add(admin)
    rider = await create_rider(db)
    trip = await create_trip(db, rider, status=TripStatus.MATCHING)
    await db.commit()

    with pytest.raises(AppError):
        await trips_service.cancel_trip(db, trip, admin, None, on_behalf_of_ops=True)


# --- Dòng thời gian đầy đủ -----------------------------------------------


async def test_dong_thoi_gian_du_de_dung_lai_ca_chuyen(db, fake_redis):
    """QA-LIFE-22: đi trọn một chuyến rồi kiểm tra dòng thời gian có đủ các mốc chính."""
    rider = await create_rider(db)
    driver, profile = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    await trips_service.mark_driver_arrived(db, trip, driver, 10.7769, 106.7009)
    await trips_service.verify_qr(db, trip, rider, profile.active_qr_token)

    kinds = [e.event_type for e in await trip_events.list_for_trip(db, trip.id)]
    assert TripEventType.DRIVER_ARRIVED in kinds
    assert TripEventType.QR_VERIFIED in kinds
    rows = (await db.execute(select(TripEvent).where(TripEvent.trip_id == trip.id))).scalars().all()
    assert all(e.created_at is not None for e in rows)


async def test_trip_out_co_moc_moi(db):
    """QA-LIFE-23: hai mốc mới phải xuất hiện trong response, nếu không app không dùng được."""
    from app.domains.trips.schemas import TripOut

    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip: Trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)

    out = TripOut.model_validate(trip)

    assert hasattr(out, "driver_arrived_at")
    assert hasattr(out, "rated_at")


# --- Đối soát phải cân cả khi có phí huỷ ---------------------------------


@pytest.mark.money
async def test_doi_soat_can_khi_co_phi_huy(db):
    """QA-LIFE-24: bài test này chặn đúng lỗi vừa gây ra khi trả phí huỷ cho tài xế.

    Phí huỷ tạo ra một khoản thu từ khách và một khoản chi cho tài xế, nhưng chuyến bị huỷ
    nên không có `final_fare`. Nếu đối soát chỉ nhìn `final_fare` thì mỗi ngày có phí huỷ là
    báo cáo lệch — và một báo cáo lệch mỗi ngày thì chẳng ai còn tin nó nữa.
    """
    from app.domains.payments import service as payments_service

    rider = await create_rider(db)
    driver, _ = await create_driver(db)
    trip = await create_trip(db, rider, driver, status=TripStatus.DRIVER_ARRIVING)
    trip.matched_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.CANCELLATION_GRACE_MINUTES + 5
    )
    await db.commit()

    await trips_service.cancel_trip(db, trip, rider, "Đổi ý")
    report = await payments_service.run_daily_reconciliation(db, datetime.now(timezone.utc).date())

    assert report.total_cancellation_fee == settings.CANCELLATION_FEE
    assert report.fare_payment_diff == Decimal("0")
    assert report.payout_wallet_diff == Decimal("0")
    assert report.balanced is True, "Đối soát phải cân khi có phí huỷ"


@pytest.mark.money
async def test_chuyen_da_danh_gia_van_nam_trong_doi_soat(db):
    """QA-LIFE-25: lỗi thật vừa gây ra khi thêm trạng thái `rated`.

    Báo cáo đối soát lọc `status == completed`, nên mỗi chuyến được khách đánh giá là biến
    mất khỏi báo cáo tài chính của ngày hôm đó — doanh thu bị khai thiếu đúng bằng số chuyến
    có đánh giá. Bài rà soát API bắt được vì `balanced` chuyển sang False.
    """
    from app.domains.payments import service as payments_service

    rider, driver, trip = await _completed_trip(db)
    trip.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await trips_service.rate_trip(db, trip, rider, 5, None)
    assert trip.status is TripStatus.RATED

    report = await payments_service.run_daily_reconciliation(db, datetime.now(timezone.utc).date())

    assert report.total_trips == 1, "Chuyến đã đánh giá vẫn phải được đếm"
    assert report.total_final_fare == Decimal("150000")


async def test_chuyen_da_danh_gia_van_duoc_dem_khi_quet_gian_lan(db):
    """QA-LIFE-26: cùng lỗi ở phía chống gian lận, nhưng hậu quả ngược lại.

    Job quét "thanh toán ngoài app" so số giờ online với số chuyến hoàn thành. Nếu chuyến
    đã đánh giá không được đếm thì tài xế nào càng được khách đánh giá nhiều lại càng bị
    cờ nhầm là gian lận.
    """
    from app.core.constants import SETTLED_TRIP_STATUSES

    rider, driver, trip = await _completed_trip(db)
    trip.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await trips_service.rate_trip(db, trip, rider, 5, None)

    assert trip.status in SETTLED_TRIP_STATUSES


async def test_gui_lai_complete_sau_khi_da_danh_gia_khong_bao_loi(db):
    """QA-LIFE-27: mất sóng khi bấm hoàn thành, khách đánh giá trước, request cũ tới sau."""
    rider, driver, trip = await _completed_trip(db)
    await trips_service.rate_trip(db, trip, rider, 5, None)

    result = await trips_service.complete_trip(db, trip, driver)

    assert result.trip.status is TripStatus.RATED
