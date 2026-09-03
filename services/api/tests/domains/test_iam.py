"""IAM nội bộ: vai trò, quyền, đăng nhập 2FA (PRD-SEC-14…18, PRD-OPS-09).

Vì sao bộ test này nặng phần "đường đi sai": một tài khoản nội bộ bị chiếm là lộ số điện thoại
và CCCD của hàng nghìn người, chứ không phải mất một chuyến xe. Những thứ được chốt cứng ở đây:

  - Sai 5 lần là khoá. Không có test thì một lần đổi thứ tự `if` trong `authenticate` đủ để
    biến ô nhập mã 6 số thành cái máy dò.
  - Thiếu quyền phải trả đúng mã quyền còn thiếu, không phải 403 trống.
  - Token của khách/tài xế không được đi lọt vào /ops, và ngược lại.
  - Vô hiệu hoá nhân sự KHÔNG được xoá dòng dữ liệu — đó là dấu vết pháp lý.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import select

from app.config import settings
from app.core.constants import UserRole
from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.security import create_access_token
from app.domains.audit.models import AuditLog
from app.domains.iam import service
from app.domains.iam.constants import ROLES, WILDCARD
from app.domains.iam.models import Permission, Role, StaffUser
from tests.conftest import create_rider

PASSWORD = "mat-khau-du-dai-12"


async def make_staff(db, *, email: str = "a@goan.vn", roles: list[str] | None = None) -> StaffUser:
    await service.sync_catalog(db)
    staff, _ = await service.create_staff(
        db,
        email=email,
        full_name="Nhân Sự Test",
        password=PASSWORD,
        role_codes=roles if roles is not None else ["super_admin"],
    )
    return staff


def totp_now(staff: StaffUser) -> str:
    assert staff.totp_secret
    return pyotp.TOTP(staff.totp_secret).now()


async def staff_headers(db, api_client, *, roles: list[str], email: str = "a@goan.vn") -> dict:
    staff = await make_staff(db, email=email, roles=roles)
    response = await api_client.post(
        "/api/v1/ops/auth/login",
        json={"email": staff.email, "password": PASSWORD, "totp_code": totp_now(staff)},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- Danh mục quyền -------------------------------------------------------------------


@pytest.mark.integration
async def test_seed_dung_12_vai_tro_theo_tai_lieu_phan_dinh(db):
    await service.sync_catalog(db)

    roles = (await db.execute(select(Role))).scalars().all()
    assert len(roles) == 12
    assert {r.code for r in roles} == set(ROLES)


@pytest.mark.integration
async def test_chay_seed_lan_hai_khong_nhan_doi_du_lieu(db):
    """Seed phải chạy được ở mỗi lần deploy mà không sinh rác."""
    first = await service.sync_catalog(db)
    second = await service.sync_catalog(db)

    assert first["roles"] == 12
    assert second == {"permissions": 0, "roles": 0, "role_permissions": 0}
    assert len((await db.execute(select(Permission))).scalars().all()) == len(
        {p.code for p in (await db.execute(select(Permission))).scalars().all()}
    )


@pytest.mark.unit
def test_khong_vai_tro_nao_vua_tao_vua_duyet_lenh_chi():
    """Maker-checker chỉ có tác dụng nếu KHÔNG ai giữ cả hai quyền (phân định §2.3)."""
    for code, (_, perms) in ROLES.items():
        if code == "super_admin":
            continue
        assert not ({"finance:payout:create", "finance:payout:approve"} <= set(perms)), code
        assert not ({"risk:penalty:propose", "risk:penalty:approve"} <= set(perms)), code


@pytest.mark.security
@pytest.mark.unit
def test_chi_super_admin_co_quyen_van_nang():
    for code, (_, perms) in ROLES.items():
        assert (WILDCARD in perms) == (code == "super_admin"), code


@pytest.mark.security
@pytest.mark.unit
def test_marketing_va_dispatcher_khong_duoc_xem_pii():
    """Tài liệu phân định ghi rõ hai vai trò này không được xem CCCD/SĐT đầy đủ."""
    for code in ("marketing", "dispatcher", "auditor"):
        assert "pii:full:read" not in ROLES[code][1]


# --- Đăng nhập ------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.integration
async def test_dang_nhap_dung_mat_khau_va_totp(db):
    staff = await make_staff(db)

    logged = await service.authenticate(
        db, email=staff.email, password=PASSWORD, totp_code=totp_now(staff)
    )

    assert logged.id == staff.id
    assert logged.last_login_at is not None
    assert logged.failed_attempts == 0


@pytest.mark.security
@pytest.mark.integration
async def test_dung_mat_khau_nhung_sai_totp_thi_khong_vao_duoc(db):
    """Lộ mật khẩu không được phép là đủ để vào — đó là toàn bộ lý do bắt buộc 2FA."""
    staff = await make_staff(db)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(db, email=staff.email, password=PASSWORD, totp_code="000000")

    await db.refresh(staff)
    assert staff.failed_attempts == 1


@pytest.mark.security
@pytest.mark.integration
async def test_sai_5_lan_thi_khoa_tai_khoan(db):
    staff = await make_staff(db)

    for _ in range(settings.STAFF_MAX_FAILED_ATTEMPTS):
        with pytest.raises(UnauthorizedError):
            await service.authenticate(
                db, email=staff.email, password="sai-mat-khau-roi", totp_code=totp_now(staff)
            )

    await db.refresh(staff)
    assert service.is_locked(staff)
    # Lần thứ 6 dù gõ ĐÚNG cũng không vào được: khoá là khoá.
    with pytest.raises(PermissionDeniedError):
        await service.authenticate(
            db, email=staff.email, password=PASSWORD, totp_code=totp_now(staff)
        )


@pytest.mark.security
@pytest.mark.integration
async def test_admin_go_khoa_som_duoc(db):
    staff = await make_staff(db)
    staff.failed_attempts = 5
    staff.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    await db.commit()

    await service.unlock(db, staff)

    assert service.is_locked(staff) is False
    assert (
        await service.authenticate(
            db, email=staff.email, password=PASSWORD, totp_code=totp_now(staff)
        )
    ).id == staff.id


@pytest.mark.security
@pytest.mark.integration
async def test_email_khong_ton_tai_bao_loi_giong_het_sai_mat_khau(db):
    """Trả lời khác nhau là chỉ cho kẻ tấn công biết email nào có thật trong công ty."""
    staff = await make_staff(db)

    with pytest.raises(UnauthorizedError) as khong_ton_tai:
        await service.authenticate(
            db, email="khong-co@goan.vn", password=PASSWORD, totp_code="123456"
        )
    with pytest.raises(UnauthorizedError) as sai_mat_khau:
        await service.authenticate(
            db, email=staff.email, password="sai-roi-nhe-123", totp_code=totp_now(staff)
        )

    assert khong_ton_tai.value.message == sai_mat_khau.value.message


@pytest.mark.security
@pytest.mark.integration
async def test_tai_khoan_bi_vo_hieu_hoa_thi_khong_dang_nhap_duoc(db):
    staff = await make_staff(db)
    await service.deactivate(db, staff, "Đã nghỉ việc")

    with pytest.raises(PermissionDeniedError):
        await service.authenticate(
            db, email=staff.email, password=PASSWORD, totp_code=totp_now(staff)
        )


@pytest.mark.security
@pytest.mark.integration
async def test_chua_thiet_lap_2fa_thi_khong_vao_duoc_du_mat_khau_dung(db):
    staff = await make_staff(db)
    staff.totp_secret = None
    await db.commit()

    with pytest.raises(PermissionDeniedError):
        await service.authenticate(db, email=staff.email, password=PASSWORD, totp_code="123456")


# --- Phân quyền -----------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.api
async def test_thieu_quyen_tra_403_kem_dung_ma_quyen_con_thieu(db, api_client):
    """403 trống khiến người vận hành không biết phải xin quyền gì."""
    headers = await staff_headers(db, api_client, roles=["dispatcher"])

    response = await api_client.get("/api/v1/ops/staff", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "iam:staff:read"


@pytest.mark.security
@pytest.mark.api
async def test_super_admin_di_qua_moi_cua(db, api_client):
    headers = await staff_headers(db, api_client, roles=["super_admin"])

    assert (await api_client.get("/api/v1/ops/staff", headers=headers)).status_code == 200
    assert (await api_client.get("/api/v1/ops/roles", headers=headers)).status_code == 200
    assert (await api_client.get("/api/v1/ops/audit-logs", headers=headers)).status_code == 200


@pytest.mark.security
@pytest.mark.api
async def test_token_cua_khach_khong_dung_duoc_cho_console(db, api_client):
    rider = await create_rider(db)
    headers = {
        "Authorization": f"Bearer {create_access_token(str(rider.id), UserRole.RIDER.value)}"
    }

    response = await api_client.get("/api/v1/ops/staff", headers=headers)

    assert response.status_code == 403


@pytest.mark.security
@pytest.mark.api
async def test_token_noi_bo_khong_dung_duoc_cho_endpoint_cua_khach(db, api_client):
    """`sub` của nhân sự nằm ở bảng staff_users nên không bao giờ khớp một người dùng app."""
    headers = await staff_headers(db, api_client, roles=["super_admin"])

    response = await api_client.get("/api/v1/trips", headers=headers)

    assert response.status_code == 401


@pytest.mark.api
async def test_me_tra_ve_danh_sach_quyen_de_console_dung_ve_menu(db, api_client):
    headers = await staff_headers(db, api_client, roles=["driver_ops"])

    body = (await api_client.get("/api/v1/ops/auth/me", headers=headers)).json()

    assert body["roles"] == ["driver_ops"]
    assert "driver:profile:approve" in body["permissions"]
    assert "finance:payout:approve" not in body["permissions"]


# --- Quản lý nhân sự ------------------------------------------------------------------


@pytest.mark.api
async def test_tao_nhan_su_tra_uri_totp_dung_mot_lan(db, api_client):
    headers = await staff_headers(db, api_client, roles=["super_admin"])

    created = await api_client.post(
        "/api/v1/ops/staff",
        headers=headers,
        json={
            "email": "moi@goan.vn",
            "full_name": "Người Mới",
            "password": "mat-khau-du-dai-12",
            "roles": ["cs_agent"],
        },
    )

    assert created.status_code == 201
    assert created.json()["totp_provisioning_uri"].startswith("otpauth://totp/")
    # Đọc lại hồ sơ thì KHÔNG được thấy bí mật TOTP ở bất kỳ đâu.
    staff_id = created.json()["staff"]["id"]
    detail = await api_client.get(f"/api/v1/ops/staff/{staff_id}", headers=headers)
    assert "totp" not in detail.text.lower()


@pytest.mark.security
@pytest.mark.api
async def test_vo_hieu_hoa_khong_xoa_du_lieu(db, api_client):
    """Xoá dòng nhân sự là mất dấu vết mọi thao tác người đó từng làm (phân định §2.3)."""
    headers = await staff_headers(db, api_client, roles=["super_admin"])
    target = await service.create_staff(
        db, email="nghi@goan.vn", full_name="Sắp Nghỉ", password=PASSWORD, role_codes=["cs_agent"]
    )
    target_id = target[0].id

    response = await api_client.post(
        f"/api/v1/ops/staff/{target_id}/deactivate",
        headers=headers,
        json={"reason": "Nghỉ việc từ 01/10"},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert await db.get(StaffUser, target_id) is not None


@pytest.mark.api
async def test_danh_sach_nhan_su_mac_dinh_an_nguoi_da_nghi(db, api_client):
    headers = await staff_headers(db, api_client, roles=["super_admin"])
    nghi, _ = await service.create_staff(
        db, email="nghi2@goan.vn", full_name="Đã Nghỉ", password=PASSWORD, role_codes=[]
    )
    await service.deactivate(db, nghi, "Nghỉ việc")

    mac_dinh = (await api_client.get("/api/v1/ops/staff", headers=headers)).json()
    day_du = (
        await api_client.get("/api/v1/ops/staff?include_inactive=true", headers=headers)
    ).json()

    assert {s["email"] for s in mac_dinh} == {"a@goan.vn"}
    assert "nghi2@goan.vn" in {s["email"] for s in day_du}


@pytest.mark.api
async def test_gan_vai_tro_khong_ton_tai_thi_404_chu_khong_am_tham_bo_qua(db, api_client):
    headers = await staff_headers(db, api_client, roles=["super_admin"])
    me = (await api_client.get("/api/v1/ops/auth/me", headers=headers)).json()

    response = await api_client.put(
        f"/api/v1/ops/staff/{me['id']}/roles",
        headers=headers,
        json={"roles": ["vai_tro_bia_dat"]},
    )

    assert response.status_code == 404


# --- Nhật ký thao tác -----------------------------------------------------------------


@pytest.mark.security
@pytest.mark.api
async def test_thao_tac_cua_nhan_su_ghi_vao_actor_staff_id(db, api_client):
    """Nhét id nhân sự vào actor_id sẽ vi phạm khoá ngoại sang users và mất luôn dòng audit."""
    headers = await staff_headers(db, api_client, roles=["super_admin"])

    await api_client.post(
        "/api/v1/ops/staff",
        headers=headers,
        json={
            "email": "ghilog@goan.vn",
            "full_name": "Ghi Log",
            "password": "mat-khau-du-dai-12",
            "roles": [],
        },
    )

    rows = (
        (await db.execute(select(AuditLog).where(AuditLog.path == "/api/v1/ops/staff")))
        .scalars()
        .all()
    )
    assert rows, "Thao tác của Console phải để lại dấu vết"
    assert rows[-1].actor_staff_id is not None
    assert rows[-1].actor_id is None
    assert rows[-1].actor_role == "staff"


@pytest.mark.api
async def test_audit_log_loc_theo_doi_tuong_va_phan_trang_bang_con_tro(db, api_client):
    headers = await staff_headers(db, api_client, roles=["auditor"], email="kt@goan.vn")
    rider = await create_rider(db)
    for i in range(3):
        db.add(
            AuditLog(
                id=uuid.uuid4(),
                actor_id=rider.id,
                actor_role="rider",
                action="POST /api/v1/trips",
                method="POST",
                path="/api/v1/trips",
                status_code=201,
                resource_type="trip",
                resource_id=str(i),
                created_at=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
        )
    await db.commit()

    trang_1 = (
        await api_client.get(f"/api/v1/ops/audit-logs?actor_id={rider.id}&limit=2", headers=headers)
    ).json()
    trang_2 = (
        await api_client.get(
            f"/api/v1/ops/audit-logs?actor_id={rider.id}&limit=2&cursor={trang_1['next_cursor']}",
            headers=headers,
        )
    ).json()

    assert len(trang_1["items"]) == 2
    assert trang_1["next_cursor"] is not None
    assert len(trang_2["items"]) == 1
    assert {i["id"] for i in trang_1["items"]}.isdisjoint({i["id"] for i in trang_2["items"]})


@pytest.mark.security
@pytest.mark.api
async def test_khong_co_quyen_doc_audit_thi_khong_doc_duoc(db, api_client):
    headers = await staff_headers(db, api_client, roles=["marketing"])

    response = await api_client.get("/api/v1/ops/audit-logs", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "audit:log:read"


# --- Phiên làm việc -------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.api
async def test_lam_moi_token_trong_phien_va_thu_hoi_khi_dung_lai_token_cu(db, api_client):
    """Xoay vòng refresh token cho tài khoản nội bộ, giống hệt phía app.

    Test này đỏ khi ai đó bỏ bước `consume` trong endpoint refresh: lúc đó một refresh token
    bị lộ dùng được mãi trong suốt phiên 8 giờ mà hệ thống không hề biết.
    """
    staff = await make_staff(db, email="phien@goan.vn")
    login = await api_client.post(
        "/api/v1/ops/auth/login",
        json={"email": staff.email, "password": PASSWORD, "totp_code": totp_now(staff)},
    )
    refresh_token = login.json()["refresh_token"]

    lan_dau = await api_client.post(
        "/api/v1/ops/auth/refresh", json={"refresh_token": refresh_token}
    )
    dung_lai = await api_client.post(
        "/api/v1/ops/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert lan_dau.status_code == 200
    assert lan_dau.json()["session_expires_in"] == settings.STAFF_SESSION_HOURS * 3600
    assert dung_lai.status_code == 401

    # Cả họ token bị thu hồi: token mới vừa cấp cũng không dùng được nữa.
    token_moi = lan_dau.json()["refresh_token"]
    sau_thu_hoi = await api_client.post(
        "/api/v1/ops/auth/refresh", json={"refresh_token": token_moi}
    )
    assert sau_thu_hoi.status_code == 401


@pytest.mark.security
@pytest.mark.api
async def test_dang_xuat_thu_hoi_ca_phien_chu_khong_chi_xoa_token_o_may(db, api_client):
    staff = await make_staff(db, email="dangxuat@goan.vn")
    login = await api_client.post(
        "/api/v1/ops/auth/login",
        json={"email": staff.email, "password": PASSWORD, "totp_code": totp_now(staff)},
    )
    refresh_token = login.json()["refresh_token"]

    await api_client.post("/api/v1/ops/auth/logout", json={"refresh_token": refresh_token})
    sau_dang_xuat = await api_client.post(
        "/api/v1/ops/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert sau_dang_xuat.status_code == 401


@pytest.mark.security
@pytest.mark.api
async def test_token_cua_app_khong_dung_duoc_o_endpoint_refresh_noi_bo(db, api_client):
    rider = await create_rider(db, phone="0909090909")
    from app.core.security import create_refresh_token

    gia_mao = create_refresh_token(str(rider.id), UserRole.RIDER.value, family="fam", jti="j")

    response = await api_client.post("/api/v1/ops/auth/refresh", json={"refresh_token": gia_mao})

    assert response.status_code == 401
