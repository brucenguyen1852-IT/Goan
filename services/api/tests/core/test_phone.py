"""QA-PHONE — chuẩn hoá số điện thoại (PRD-SEC-12)."""

import pytest

from app.core.phone import InvalidPhoneError, normalize_phone

pytestmark = [pytest.mark.unit, pytest.mark.prd]


@pytest.mark.parametrize(
    "raw",
    ["0912345678", "+84912345678", "84912345678", "0912 345 678", " 0912345678 ", "091-234-5678"],
)
def test_cac_cach_nhap_deu_ve_mot_so(raw):
    """QA-PHONE-01: cùng một người nhập kiểu nào cũng phải ra một tài khoản.

    Không chuẩn hoá thì mỗi cách nhập tạo một tài khoản riêng — ví, ký quỹ và lịch sử
    chuyến bị chia đôi. Đây là loại lỗi rất khó gỡ khi đã có dữ liệu thật.
    """
    assert normalize_phone(raw) == "0912345678"


@pytest.mark.parametrize(
    "raw,vi_sao",
    [
        ("khong-phai-so", "không có chữ số"),
        ("091234", "quá ngắn"),
        ("09123456789", "quá dài"),
        ("1912345678", "không bắt đầu bằng 0"),
        ("", "rỗng"),
        ("   ", "chỉ có khoảng trắng"),
    ],
)
def test_tu_choi_so_khong_hop_le(raw, vi_sao):
    """QA-PHONE-02: mỗi lần gửi OTP là một tin SMS tốn tiền — không được gửi tới rác."""
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_thong_bao_loi_du_ro_de_nguoi_dung_sua_duoc():
    """QA-PHONE-03: lỗi phải nói cần nhập thế nào, không chỉ nói là sai."""
    with pytest.raises(InvalidPhoneError) as exc:
        normalize_phone("091234")
    assert "0912345678" in str(exc.value)
