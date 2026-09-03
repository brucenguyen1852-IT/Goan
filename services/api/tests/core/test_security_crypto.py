"""QA-SEC — mã hoá CCCD at-rest và che PII. Ánh xạ PRD: PRD-SEC-05 (Nghị định 13/2023)."""

import pytest

from app.core import security

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.prd]


@pytest.mark.parametrize(
    "national_id",
    ["079201001234", "001099012345", "1", "0" * 12],
)
def test_ma_hoa_giai_ma_khu_hoi(national_id):
    """QA-SEC-05a: giải mã phải ra đúng số gốc, kể cả chuỗi ngắn hoặc toàn số 0."""
    token = security.encrypt_national_id(national_id)
    assert security.decrypt_national_id(token) == national_id


def test_ban_ma_khong_lo_so_goc():
    """QA-SEC-05b: nhìn vào DB không được đọc ra số CCCD."""
    national_id = "079201001234"
    token = security.encrypt_national_id(national_id)
    assert national_id not in token


def test_hai_so_khac_nhau_cho_ban_ma_khac_nhau():
    assert security.encrypt_national_id("079201001234") != security.encrypt_national_id(
        "079201001235"
    )


def test_che_chi_lo_bon_so_cuoi():
    """QA-SEC-05c: màn hình nội bộ chỉ được thấy 4 số cuối khi chưa nhập lý do."""
    masked = security.mask_national_id("079201001234")
    assert masked is not None
    assert masked.endswith("1234")
    assert "0792" not in masked


def test_che_gia_tri_rong():
    assert security.mask_national_id(None) is None


def test_token_khong_bi_lan_loai():
    """QA-SEC-05d: access token không được dùng ở chỗ đòi refresh token và ngược lại."""
    from app.core.exceptions import UnauthorizedError

    access = security.create_access_token("user-1", "rider")
    with pytest.raises(UnauthorizedError):
        security.decode_token(access, expected_type=security.REFRESH_TOKEN)


def test_token_gia_bi_tu_choi():
    from app.core.exceptions import UnauthorizedError

    with pytest.raises(UnauthorizedError):
        security.decode_token("day.khong.phai.jwt")


def test_moi_token_co_jti_rieng():
    """QA-SEC-05e: jti trùng nhau thì cơ chế phát hiện tái sử dụng sẽ hỏng."""
    jtis = {security.new_jti() for _ in range(200)}
    assert len(jtis) == 200
