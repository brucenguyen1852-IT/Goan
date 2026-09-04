"""Bề mặt API tách theo đối tượng (PRD-ARCH-01) — P1-08.

Vì sao cần test: bảng `AUDIENCES` là câu trả lời cho "endpoint này của ai?". Nếu thêm endpoint
mới mà quên khai báo, nó sẽ im lặng không xuất hiện ở nhóm nào và không ai phát hiện — đúng
kiểu lỗi chỉ lộ ra khi app tài xế gọi một đường dẫn không tồn tại.
"""

import pytest

from app.api import AUDIENCE_NAMES, AUDIENCES, unassigned_routes
from app.domains.auth.router import router as auth_router
from app.domains.chat.router import router as chat_router
from app.domains.escrow.router import router as escrow_router
from app.domains.fraud.router import router as fraud_router
from app.domains.matching.router import router as matching_router
from app.domains.partners.router import router as partners_router
from app.domains.payments.router import router as payments_router
from app.domains.pricing.router import router as pricing_router
from app.domains.support.router import router as support_router
from app.domains.trips.router import router as trips_router
from app.domains.users.router import router as users_router

DOMAIN_ROUTERS = [
    auth_router,
    users_router,
    pricing_router,
    trips_router,
    matching_router,
    escrow_router,
    payments_router,
    partners_router,
    fraud_router,
    chat_router,
    support_router,
]


@pytest.mark.unit
def test_moi_endpoint_nghiep_vu_deu_thuoc_mot_nhom_doi_tuong():
    """Thêm endpoint mà quên khai báo nhóm thì test này đỏ, kèm tên endpoint còn thiếu."""
    assert unassigned_routes(DOMAIN_ROUTERS) == []


@pytest.mark.unit
def test_khong_khai_bao_nhom_la_lac():
    for name, audiences in AUDIENCES.items():
        assert audiences, name
        for audience in audiences:
            assert audience in AUDIENCE_NAMES, f"{name} khai nhóm lạ: {audience}"


@pytest.mark.api
async def test_duong_dan_moi_va_duong_dan_cu_chay_cung_mot_handler(db, api_client):
    """Đường dẫn cũ phải sống tiếp: app khách đang chạy thật trên đó."""
    cu = await api_client.post("/api/v1/auth/request-otp", json={"phone": "0901000009"})
    moi = await api_client.post("/api/v1/public/auth/request-otp", json={"phone": "0901000009"})

    assert cu.status_code == moi.status_code == 200
    assert "debug_otp" in cu.json() and "debug_otp" in moi.json()


@pytest.mark.security
@pytest.mark.api
async def test_duong_dan_moi_giu_nguyen_lop_quyen(db, api_client):
    """Đổi tiền tố không được làm mất kiểm quyền — cùng handler, cùng dependency."""
    khong_token = await api_client.get("/api/v1/rider/trips")
    khong_token_cu = await api_client.get("/api/v1/trips")

    assert khong_token.status_code == khong_token_cu.status_code == 401


@pytest.mark.api
async def test_openapi_danh_dau_duong_dan_cu_la_deprecated(db, api_client):
    spec = (await api_client.get("/openapi.json")).json()

    assert spec["paths"]["/api/v1/trips"]["post"]["deprecated"] is True
    assert spec["paths"]["/api/v1/rider/trips"]["post"].get("deprecated") is not True


@pytest.mark.unit
def test_du_ca_nam_nhom_ke_ca_nhom_chua_co_endpoint():
    """Partner Portal là P6; nhóm `partner` vẫn phải tồn tại sẵn trong mã."""
    from app.api import build_audience_routers

    built = build_audience_routers(DOMAIN_ROUTERS)

    assert set(built) == set(AUDIENCE_NAMES)
    assert built["partner"].routes == [], "P6 mới thêm endpoint cho đối tác"
    for co_endpoint in ("rider", "driver", "public"):
        assert built[co_endpoint].routes, co_endpoint
