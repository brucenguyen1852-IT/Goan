"""Che dữ liệu cá nhân khi hiển thị cho nhân sự nội bộ (phân định §2.3, Nghị định 13).

Nguyên tắc: **che là mặc định**, xem đầy đủ là ngoại lệ và phải nêu lý do. Lý do không phải
thủ tục hành chính — nó là thứ duy nhất phân biệt được "CSKH tra số để gọi lại cho khách"
với "nhân viên bán danh sách khách hàng ra ngoài", và cả hai đều để lại đúng một dòng log
giống hệt nhau nếu không có lý do.

Che ở đây là che khi HIỂN THỊ. CCCD còn được mã hoá at-rest ở `core/security.py` — hai lớp
khác nhau, cần cả hai.
"""

from __future__ import annotations


def mask_phone(phone: str | None) -> str | None:
    """0912345678 -> 0912***678. Giữ đủ đầu số và 3 số cuối để đối chiếu khi khách đọc lên."""
    if not phone:
        return None
    if len(phone) <= 7:
        return "*" * len(phone)
    return f"{phone[:4]}{'*' * (len(phone) - 7)}{phone[-3:]}"


def mask_email(email: str | None) -> str | None:
    """nguyenvana@goan.vn -> ngu***@goan.vn."""
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    keep = local[:3] if len(local) > 3 else local[:1]
    return f"{keep}***@{domain}"


def mask_name(full_name: str | None) -> str | None:
    """Giữ họ và tên cuối, che tên đệm: 'Nguyễn Văn An' -> 'Nguyễn *** An'."""
    if not full_name:
        return None
    parts = full_name.split()
    if len(parts) <= 2:
        return full_name
    return f"{parts[0]} {'*' * 3} {parts[-1]}"
