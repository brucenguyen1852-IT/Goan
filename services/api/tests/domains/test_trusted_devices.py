"""Nhớ thiết bị 30 ngày và sửa quyền vai trò từ Console (PRD-SEC-21, PRD-OPS-15).

Nhớ thiết bị là đánh đổi có chủ đích: bắt gõ mã 6 số mỗi ca làm việc thì người ta sẽ tìm cách
lách — thường là dán mã dự phòng lên màn hình, tệ hơn nhiều. Nhưng đánh đổi chỉ chấp nhận được
khi ba ràng buộc dưới đây đứng vững, và đây là chỗ chốt chúng.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.exceptions import NotFoundError, PermissionDeniedError, UnauthorizedError
from app.domains.iam import service
from app.domains.iam.models import Role, TrustedDevice
from tests.domains.test_iam import PASSWORD, make_staff, staff_headers, totp_now


@pytest.mark.security
@pytest.mark.integration
async def test_thiet_bi_da_nho_thi_lan_sau_khong_phai_nhap_ma(db):
    staff = await make_staff(db, email="nho@goan.vn")
    token = await service.remember_device(db, staff, label="MacBook của Bruce")

    logged = await service.authenticate(
        db, email=staff.email, password=PASSWORD, device_token=token
    )

    assert logged.id == staff.id


@pytest.mark.security
@pytest.mark.integration
async def test_nho_thiet_bi_khong_bao_gio_bo_qua_mat_khau(db):
    """Nhớ thiết bị là đỡ phiền lúc gõ mã, không phải biến máy công ty thành chìa khoá vạn năng."""
    staff = await make_staff(db, email="nho2@goan.vn")
    token = await service.remember_device(db, staff)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(
            db, email=staff.email, password="mat-khau-sai-roi", device_token=token
        )


@pytest.mark.security
@pytest.mark.integration
async def test_token_thiet_bi_cua_nguoi_khac_khong_dung_duoc(db):
    a = await make_staff(db, email="a-dev@goan.vn")
    b = await make_staff(db, email="b-dev@goan.vn")
    token_cua_a = await service.remember_device(db, a)

    assert await service.find_trusted_device(db, b, token_cua_a) is None
    with pytest.raises(UnauthorizedError):
        await service.authenticate(db, email=b.email, password=PASSWORD, device_token=token_cua_a)


@pytest.mark.security
@pytest.mark.integration
async def test_het_han_30_ngay_thi_phai_nhap_ma_lai(db):
    staff = await make_staff(db, email="hethan@goan.vn")
    token = await service.remember_device(db, staff)
    device = (await db.execute(select(TrustedDevice))).scalar_one()
    device.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()

    assert await service.find_trusted_device(db, staff, token) is None
    with pytest.raises(UnauthorizedError):
        await service.authenticate(db, email=staff.email, password=PASSWORD, device_token=token)


@pytest.mark.security
@pytest.mark.integration
async def test_go_thiet_bi_thi_token_cu_chet_ngay(db):
    """Mất máy mà không gỡ được ngay thì cả cơ chế này thành lỗ hổng."""
    staff = await make_staff(db, email="matmay@goan.vn")
    token = await service.remember_device(db, staff)

    assert await service.revoke_devices(db, staff) == 1

    assert await service.find_trusted_device(db, staff, token) is None
    assert await service.list_devices(db, staff) == []


@pytest.mark.security
@pytest.mark.integration
async def test_khong_luu_token_tho_trong_co_so_du_lieu(db):
    staff = await make_staff(db, email="hash@goan.vn")
    token = await service.remember_device(db, staff)

    device = (await db.execute(select(TrustedDevice))).scalar_one()

    assert token not in device.token_hash
    assert len(device.token_hash) == 64


@pytest.mark.security
@pytest.mark.api
async def test_luong_nho_thiet_bi_qua_http(db, api_client):
    staff = await make_staff(db, email="http-dev@goan.vn")

    lan_dau = await api_client.post(
        "/api/v1/ops/auth/login",
        json={
            "email": staff.email,
            "password": PASSWORD,
            "totp_code": totp_now(staff),
            "remember_device": True,
            "device_label": "Máy bàn phòng điều phối",
        },
    )
    device_token = lan_dau.json()["device_token"]
    lan_sau = await api_client.post(
        "/api/v1/ops/auth/login",
        json={"email": staff.email, "password": PASSWORD, "device_token": device_token},
    )

    assert lan_dau.status_code == 200
    assert device_token
    assert lan_sau.status_code == 200, lan_sau.text
    # Không bật nhớ thì không cấp thêm token mới.
    assert lan_sau.json()["device_token"] is None


@pytest.mark.security
@pytest.mark.api
async def test_khong_gui_gi_ca_thi_van_phai_nhap_ma(db, api_client):
    staff = await make_staff(db, email="thieuma@goan.vn")

    response = await api_client.post(
        "/api/v1/ops/auth/login", json={"email": staff.email, "password": PASSWORD}
    )

    assert response.status_code == 401


# --- P1-15: sửa quyền vai trò từ Console ----------------------------------------------


@pytest.mark.security
@pytest.mark.integration
async def test_doi_quyen_cua_vai_tro_khong_can_deploy(db):
    await make_staff(db, email="admin-role@goan.vn")
    role = await service.get_role(db, "dispatcher")

    await service.set_role_permissions(db, role, ["ops:fleet:read", "trip:trip:read_all"])

    updated = await service.get_role(db, "dispatcher")
    assert {p.code for p in updated.permissions} == {"ops:fleet:read", "trip:trip:read_all"}


@pytest.mark.security
@pytest.mark.integration
async def test_khong_ai_sua_duoc_quyen_cua_super_admin(db):
    """Gỡ quyền của super_admin là khoá cả công ty ra ngoài, không sửa được nếu không vào DB."""
    await make_staff(db, email="admin-role2@goan.vn")
    role = await service.get_role(db, "super_admin")

    with pytest.raises(PermissionDeniedError):
        await service.set_role_permissions(db, role, ["ops:fleet:read"])


@pytest.mark.security
@pytest.mark.integration
async def test_khong_gan_duoc_quyen_van_nang_cho_vai_tro_thuong(db):
    await make_staff(db, email="admin-role3@goan.vn")
    role = await service.get_role(db, "marketing")

    with pytest.raises(PermissionDeniedError):
        await service.set_role_permissions(db, role, ["*"])


@pytest.mark.integration
async def test_gan_quyen_khong_ton_tai_thi_bao_loi_ro_rang(db):
    await make_staff(db, email="admin-role4@goan.vn")
    role = await service.get_role(db, "marketing")

    with pytest.raises(NotFoundError) as err:
        await service.set_role_permissions(db, role, ["quyen:bia:dat"])

    assert err.value.details["permissions"] == ["quyen:bia:dat"]


@pytest.mark.security
@pytest.mark.api
async def test_sua_quyen_vai_tro_qua_http_va_co_hieu_luc_ngay(db, api_client):
    headers = await staff_headers(db, api_client, roles=["super_admin"], email="root@goan.vn")

    truoc = (await api_client.get("/api/v1/ops/roles", headers=headers)).json()
    doi = await api_client.put(
        "/api/v1/ops/roles/marketing/permissions",
        headers=headers,
        json={"permissions": ["pricing:rule:write"]},
    )
    danh_muc = await api_client.get("/api/v1/ops/permissions", headers=headers)

    assert doi.status_code == 200
    assert doi.json()["permissions"] == ["pricing:rule:write"]
    assert any(r["code"] == "marketing" for r in truoc)
    assert danh_muc.status_code == 200
    assert all(p["code"] != "*" for p in danh_muc.json()), "Quyền vạn năng không được liệt kê"


@pytest.mark.security
@pytest.mark.api
async def test_thieu_quyen_iam_role_write_thi_khong_sua_duoc(db, api_client):
    headers = await staff_headers(db, api_client, roles=["auditor"], email="kiemtoan@goan.vn")

    response = await api_client.put(
        "/api/v1/ops/roles/marketing/permissions",
        headers=headers,
        json={"permissions": ["pricing:rule:write"]},
    )

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "iam:role:write"


@pytest.mark.integration
async def test_vai_tro_khong_ton_tai_thi_404(db):
    await make_staff(db, email="admin-role5@goan.vn")

    with pytest.raises(NotFoundError):
        await service.get_role(db, "vai_tro_bia_dat")

    assert (await db.execute(select(Role).where(Role.code == "vai_tro_bia_dat"))).first() is None
