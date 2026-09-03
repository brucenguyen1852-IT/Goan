"""Chuẩn hoá số điện thoại Việt Nam.

Vì sao cần: cùng một người có thể nhập "0912345678", "+84912345678", "84912345678" hoặc
"0912 345 678". Nếu không chuẩn hoá, mỗi cách nhập tạo một tài khoản riêng — ví, ký quỹ và
lịch sử chuyến của họ bị chia đôi, và đó là loại lỗi rất khó gỡ khi đã có dữ liệu thật.

Dạng chuẩn dùng trong toàn hệ thống: 0 + 9 chữ số (10 ký tự), đúng chuẩn đầu số di động
Việt Nam sau đợt chuyển đổi 11 số về 10 số.
"""

import re

_NON_DIGIT = re.compile(r"[^\d+]")
VN_MOBILE = re.compile(r"^0\d{9}$")


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Trả về dạng chuẩn 0XXXXXXXXX. Ném InvalidPhoneError nếu không phải số VN hợp lệ."""
    if not raw:
        raise InvalidPhoneError("Số điện thoại không được để trống")

    cleaned = _NON_DIGIT.sub("", raw.strip())

    if cleaned.startswith("+84"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("84") and len(cleaned) == 11:
        cleaned = "0" + cleaned[2:]

    if not VN_MOBILE.match(cleaned):
        raise InvalidPhoneError(
            "Số điện thoại không hợp lệ. Cần 10 số bắt đầu bằng 0 (vd: 0912345678)"
        )
    return cleaned
