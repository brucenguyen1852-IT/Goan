"""Tiện ích tiền tệ VNĐ (SPEC 13): luôn Decimal, làm tròn ROUND_HALF_UP về số nguyên đồng."""

from decimal import Decimal, ROUND_HALF_UP

VND = Decimal("1")
ZERO = Decimal("0")


def vnd(value: Decimal | int | float | str) -> Decimal:
    """Chuẩn hoá về VNĐ nguyên. Không nhận float trực tiếp trong logic nghiệp vụ,
    nhưng vẫn chấp nhận ở biên (input API) bằng cách đi qua str để tránh sai số nhị phân."""
    if isinstance(value, float):
        value = str(value)
    return Decimal(value).quantize(VND, rounding=ROUND_HALF_UP)
