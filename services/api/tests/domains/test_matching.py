"""QA-MATCH — ghép chuyến. Ánh xạ PRD: PRD-MATCH-01/02/03.

Ba yêu cầu này trước đây có code nhưng không có test — tức là không ai chứng minh được
bán kính có thực sự nới, hay hai tài xế bấm cùng lúc thì có thật sự chỉ một người thắng.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.core.constants import OnlineStatus, TripStatus, UserStatus
from app.core.exceptions import ConflictError, PermissionDeniedError
from app.domains.matching import service as matching
from app.redis_client import DRIVER_GEO_KEY
from tests.conftest import create_driver, create_rider, create_trip

pytestmark = [pytest.mark.integration, pytest.mark.prd]

PICKUP_LAT, PICKUP_LNG = 10.7760, 106.7000


def _offset_km(lat: float, km: float) -> float:
    """Dịch vĩ độ đi xấp xỉ `km` (1 độ vĩ ≈ 111 km)."""
    return lat + km / 111.0


async def _place(redis, driver_id: uuid.UUID, km_away: float) -> None:
    await redis.geoadd(
        DRIVER_GEO_KEY, [PICKUP_LNG, _offset_km(PICKUP_LAT, km_away), str(driver_id)]
    )


async def test_tim_thay_tai_xe_trong_ban_kinh_gan(db, fake_redis):
    """QA-MATCH-01: tài xế cách 2km phải được tìm thấy ngay ở vòng đầu."""
    driver, _ = await create_driver(db)
    await _place(fake_redis, driver.id, 2)

    found = await matching.find_nearby_drivers(db, fake_redis, lat=PICKUP_LAT, lng=PICKUP_LNG)

    assert [d.driver_id for d in found] == [driver.id]


async def test_noi_dan_ban_kinh_khi_khong_co_ai_o_gan(db, fake_redis):
    """QA-MATCH-02: tài xế cách 10km chỉ tìm thấy ở vòng 12km — chứng minh bán kính có nới thật.

    Nếu code chỉ tìm một vòng 5km thì test này đỏ.
    """
    driver, _ = await create_driver(db)
    await _place(fake_redis, driver.id, 10)
    assert settings.MATCHING_RADIUS_STEPS_KM == [5, 8, 12]

    found = await matching.find_nearby_drivers(db, fake_redis, lat=PICKUP_LAT, lng=PICKUP_LNG)

    assert [d.driver_id for d in found] == [driver.id]


async def test_khong_tim_thay_ai_ngoai_ban_kinh_toi_da(db, fake_redis):
    """QA-MATCH-03: tài xế cách 30km không được ghép — trợ cấp đón xa cũng không cứu nổi."""
    driver, _ = await create_driver(db)
    await _place(fake_redis, driver.id, 30)

    found = await matching.find_nearby_drivers(db, fake_redis, lat=PICKUP_LAT, lng=PICKUP_LNG)

    assert found == []


async def test_uu_tien_tai_xe_gan_hon(db, fake_redis):
    """QA-MATCH-04: danh sách offer phải sắp theo khoảng cách tăng dần."""
    near, _ = await create_driver(db, phone="0900000010")
    far, _ = await create_driver(db, phone="0900000011")
    await _place(fake_redis, far.id, 4)
    await _place(fake_redis, near.id, 1)

    found = await matching.find_nearby_drivers(db, fake_redis, lat=PICKUP_LAT, lng=PICKUP_LNG)

    assert [d.driver_id for d in found] == [near.id, far.id]


@pytest.mark.parametrize(
    "mutate,ly_do",
    [
        (lambda p, u: setattr(p, "online_status", OnlineStatus.ON_TRIP), "đang chạy chuyến khác"),
        (lambda p, u: setattr(p, "online_status", OnlineStatus.OFFLINE), "đã tắt ca"),
        (lambda p, u: setattr(p, "fraud_strikes", 3), "quá ngưỡng cảnh cáo gian lận"),
        (lambda p, u: setattr(u, "status", UserStatus.BANNED), "tài khoản bị khoá"),
    ],
)
async def test_loai_tai_xe_khong_du_dieu_kien(db, fake_redis, mutate, ly_do):
    """QA-MATCH-05: tài xế không đủ điều kiện thì dù ở ngay cạnh cũng không nhận được cuốc."""
    user, profile = await create_driver(db)
    mutate(profile, user)
    await db.commit()
    await _place(fake_redis, user.id, 1)

    found = await matching.find_nearby_drivers(db, fake_redis, lat=PICKUP_LAT, lng=PICKUP_LNG)

    assert found == [], f"Phải loại tài xế {ly_do}"


@pytest.mark.security
async def test_chi_mot_tai_xe_thang_khi_cung_nhan(db, fake_redis):
    """QA-MATCH-06: hai tài xế bấm nhận cùng lúc — chỉ một người được chuyến.

    Đây là lỗi kinh điển của hệ thống đặt xe: hai tài xế cùng chạy tới một điểm đón,
    một người mất công vô ích và khách thì bối rối.
    """
    rider = await create_rider(db)
    d1, _ = await create_driver(db, phone="0900000021")
    d2, _ = await create_driver(db, phone="0900000022")
    trip = await create_trip(db, rider, status=TripStatus.MATCHING)

    await matching.accept_offer(db, fake_redis, trip, d1.id)

    with pytest.raises(ConflictError):
        await matching.accept_offer(db, fake_redis, trip, d2.id)

    assert trip.driver_id == d1.id


@pytest.mark.security
async def test_tai_xe_ngoai_danh_sach_moi_khong_nhan_duoc(db, fake_redis):
    """QA-MATCH-07: không thể tự gọi API để cướp chuyến của người khác."""
    from app.redis_client import TRIP_OFFER_KEY

    rider = await create_rider(db)
    invited, _ = await create_driver(db, phone="0900000031")
    outsider, _ = await create_driver(db, phone="0900000032")
    trip = await create_trip(db, rider, status=TripStatus.MATCHING)
    await fake_redis.sadd(TRIP_OFFER_KEY.format(trip_id=trip.id), str(invited.id))

    with pytest.raises(PermissionDeniedError):
        await matching.accept_offer(db, fake_redis, trip, outsider.id)


async def test_qua_han_khong_ai_nhan_thi_bao_khong_co_tai_xe(db, fake_redis):
    """QA-MATCH-08: quá 90 giây thì chuyến phải thoát khỏi trạng thái chờ.

    Nếu không, khách ngồi nhìn màn hình quay mãi mà không biết nên đặt lại hay không.
    """
    rider = await create_rider(db)
    trip = await create_trip(db, rider, status=TripStatus.MATCHING)
    trip.requested_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.MATCHING_TIMEOUT_SECONDS + 30
    )
    await db.commit()

    processed = await matching.expire_stale_matching_trips(db)

    assert processed == 1
    assert trip.status is TripStatus.NO_DRIVER_FOUND


async def test_chuyen_moi_dat_chua_qua_han_thi_van_cho(db, fake_redis):
    """QA-MATCH-09: đừng huỷ chuyến vừa đặt 5 giây trước."""
    rider = await create_rider(db)
    trip = await create_trip(db, rider, status=TripStatus.MATCHING)
    trip.requested_at = datetime.now(timezone.utc)
    await db.commit()

    assert await matching.expire_stale_matching_trips(db) == 0
    assert trip.status is TripStatus.MATCHING
