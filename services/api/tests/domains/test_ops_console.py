"""API vận hành cho Console: bản đồ đội xe, duyệt hồ sơ, tra cứu chuyến (PRD-OPS-11…13).

Điểm chung của cả ba nhóm endpoint này: chúng mở dữ liệu của TOÀN hệ thống cho một người
ngồi trong văn phòng. Vì vậy mỗi endpoint đều phải trả lời được hai câu: ai được xem, và
người xem thấy được đến mức nào. Test dưới đây chốt cả hai.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.constants import DriverApprovalStatus, OnlineStatus, TripStatus, UserStatus
from app.core.security import encrypt_national_id
from tests.conftest import create_driver, create_rider, create_trip
from tests.domains.test_iam import staff_headers

LY_DO = "Ảnh giấy phép lái xe mờ, không đọc được số"


@pytest.mark.api
async def test_ban_do_doi_xe_dem_dung_so_tai_xe_va_chuyen_dang_chay(db, api_client):
    headers = await staff_headers(db, api_client, roles=["dispatcher"])
    rider = await create_rider(db, phone="0911111111")
    driver_user, profile = await create_driver(db, phone="0922222222")
    profile.online_status = OnlineStatus.ON_TRIP
    await db.commit()
    await create_trip(db, rider, driver_user, status=TripStatus.IN_PROGRESS)

    body = (await api_client.get("/api/v1/ops/fleet", headers=headers)).json()

    assert body["drivers_on_trip"] == 1
    assert body["trips_active"] == 1
    assert len(body["drivers"]) == 1
    assert body["drivers"][0]["current_trip_id"] is not None


@pytest.mark.security
@pytest.mark.api
async def test_ban_do_doi_xe_khong_kem_so_dien_thoai(db, api_client):
    """Bản đồ không cần PII. Muốn gọi tài xế thì đi qua reveal-pii và để lại lý do."""
    headers = await staff_headers(db, api_client, roles=["dispatcher"])
    await create_driver(db, phone="0922222222")

    body = (await api_client.get("/api/v1/ops/fleet", headers=headers)).text

    assert "0922222222" not in body


@pytest.mark.security
@pytest.mark.api
async def test_khong_co_quyen_thi_khong_xem_duoc_ban_do(db, api_client):
    headers = await staff_headers(db, api_client, roles=["finance_accountant"])

    response = await api_client.get("/api/v1/ops/fleet", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "ops:fleet:read"


@pytest.mark.api
async def test_duyet_ho_so_tai_xe_tu_dau_den_cuoi(db, api_client):
    """DoD của P1-10: duyệt được một hồ sơ từ đầu đến cuối mà không đụng vào DB."""
    headers = await staff_headers(db, api_client, roles=["driver_ops"])
    driver_user, profile = await create_driver(db, phone="0933333333")
    profile.approval_status = DriverApprovalStatus.PENDING
    driver_user.national_id_number = encrypt_national_id("079123456789")
    await db.commit()

    cho_duyet = (
        await api_client.get("/api/v1/ops/drivers?approval_status=pending", headers=headers)
    ).json()
    duyet = await api_client.post(
        f"/api/v1/ops/drivers/{driver_user.id}/approve",
        headers=headers,
        json={"note": "Giấy tờ hợp lệ"},
    )

    assert len(cho_duyet) == 1
    assert cho_duyet[0]["national_id_masked"] == "********6789"
    assert duyet.status_code == 200
    assert duyet.json()["approval_status"] == "approved"
    assert duyet.json()["approved_at"] is not None


@pytest.mark.api
async def test_duyet_hai_lan_thi_bao_xung_dot(db, api_client):
    headers = await staff_headers(db, api_client, roles=["driver_ops"])
    driver_user, profile = await create_driver(db, phone="0933333334")
    profile.approval_status = DriverApprovalStatus.PENDING
    await db.commit()

    await api_client.post(f"/api/v1/ops/drivers/{driver_user.id}/approve", headers=headers, json={})
    lan_hai = await api_client.post(
        f"/api/v1/ops/drivers/{driver_user.id}/approve", headers=headers, json={}
    )

    assert lan_hai.status_code == 409


@pytest.mark.api
async def test_tu_choi_ho_so_bat_buoc_co_ly_do(db, api_client):
    """Từ chối không kèm lý do thì tài xế nộp lại y hệt, và Driver Ops làm lại từ đầu."""
    headers = await staff_headers(db, api_client, roles=["driver_ops"])
    driver_user, _ = await create_driver(db, phone="0933333335")

    thieu_ly_do = await api_client.post(
        f"/api/v1/ops/drivers/{driver_user.id}/reject", headers=headers, json={}
    )
    co_ly_do = await api_client.post(
        f"/api/v1/ops/drivers/{driver_user.id}/reject", headers=headers, json={"reason": LY_DO}
    )

    assert thieu_ly_do.status_code == 422
    assert co_ly_do.status_code == 200
    assert co_ly_do.json()["approval_status"] == "rejected"
    assert co_ly_do.json()["approval_note"] == LY_DO


@pytest.mark.security
@pytest.mark.api
async def test_khoa_tai_xe_thi_xoa_luon_qr_dang_song(db, api_client):
    """Khoá tài khoản mà QR còn hiệu lực thì tài xế vẫn quét được và vẫn chạy chuyến."""
    headers = await staff_headers(db, api_client, roles=["driver_ops"])
    driver_user, profile = await create_driver(db, phone="0933333336", qr_token="qr-con-song")

    response = await api_client.post(
        f"/api/v1/ops/drivers/{driver_user.id}/lock",
        headers=headers,
        json={"reason": "Nghi ngờ gian lận, đang điều tra"},
    )

    await db.refresh(profile)
    await db.refresh(driver_user)
    assert response.status_code == 200
    assert driver_user.status is UserStatus.SUSPENDED
    assert profile.active_qr_token is None
    assert profile.online_status is OnlineStatus.OFFLINE


@pytest.mark.security
@pytest.mark.api
async def test_dieu_phoi_khong_duoc_duyet_ho_so_tai_xe(db, api_client):
    headers = await staff_headers(db, api_client, roles=["dispatcher"])
    driver_user, _ = await create_driver(db, phone="0933333337")

    response = await api_client.post(
        f"/api/v1/ops/drivers/{driver_user.id}/approve", headers=headers, json={}
    )

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "driver:profile:approve"


@pytest.mark.api
async def test_tra_cuu_chuyen_loc_va_phan_trang(db, api_client):
    headers = await staff_headers(db, api_client, roles=["ops_manager"])
    rider = await create_rider(db, phone="0911111112")
    driver_user, _ = await create_driver(db, phone="0922222223")
    for _ in range(3):
        await create_trip(db, rider, driver_user, status=TripStatus.COMPLETED)
    await create_trip(db, rider, driver_user, status=TripStatus.CANCELLED_BY_RIDER)

    trang_1 = (await api_client.get("/api/v1/ops/trips?limit=2", headers=headers)).json()
    hoan_thanh = (
        await api_client.get("/api/v1/ops/trips?status=completed", headers=headers)
    ).json()

    assert len(trang_1["items"]) == 2
    assert trang_1["next_cursor"] is not None
    assert len(hoan_thanh["items"]) == 3


@pytest.mark.api
async def test_tua_lai_lo_trinh_mot_chuyen(db, api_client):
    """DoD của P1-11: xem lại được lộ trình một chuyến đã hoàn thành."""
    from app.domains.trips.models import TripGpsLog

    headers = await staff_headers(db, api_client, roles=["ops_manager"])
    rider = await create_rider(db, phone="0911111113")
    driver_user, _ = await create_driver(db, phone="0922222224")
    trip = await create_trip(db, rider, driver_user, status=TripStatus.COMPLETED)
    base = datetime.now(timezone.utc)
    for i in range(3):
        db.add(
            TripGpsLog(
                trip_id=trip.id,
                lat=10.77 + i / 1000,
                lng=106.70 + i / 1000,
                recorded_at=base + timedelta(minutes=i),
            )
        )
    await db.commit()

    points = (await api_client.get(f"/api/v1/ops/trips/{trip.id}/gps", headers=headers)).json()

    assert len(points) == 3
    assert points[0]["lat"] < points[-1]["lat"], "Phải trả về theo đúng thứ tự thời gian"


@pytest.mark.money
@pytest.mark.api
async def test_so_lieu_dau_trang_tinh_ca_chuyen_da_danh_gia(db, api_client):
    """Bài học cũ: lọc status == completed làm chuyến đã đánh giá biến mất khỏi báo cáo."""
    headers = await staff_headers(db, api_client, roles=["ops_manager"])
    rider = await create_rider(db, phone="0911111114")
    driver_user, _ = await create_driver(db, phone="0922222225")
    hoan_thanh = await create_trip(db, rider, driver_user, status=TripStatus.COMPLETED)
    da_danh_gia = await create_trip(db, rider, driver_user, status=TripStatus.RATED)
    hoan_thanh.platform_commission = Decimal("38000")
    da_danh_gia.platform_commission = Decimal("38000")
    await db.commit()

    stats = (await api_client.get("/api/v1/ops/stats/today", headers=headers)).json()

    assert stats["trips_settled"] == 2
    assert stats["platform_commission_total"] == "76000"
