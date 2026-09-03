#!/usr/bin/env python3
"""Tạo tài khoản quản trị. Chạy trên máy chủ, không có endpoint công khai tương ứng.

Vì sao không làm bằng API: đăng ký công khai chỉ cho phép vai trò khách và tài xế
(app/domains/auth/service.py::PUBLIC_SIGNUP_ROLES). Nếu có endpoint tạo admin thì chính nó
phải tự bảo vệ, và đó là chỗ dễ hổng nhất. Cho tới khi có module IAM ở giai đoạn P1, tài
khoản nội bộ được tạo thủ công trên máy chủ.

    python -m scripts.create_admin 0900000000 "Nguyễn Văn Quản Trị"

Sau khi tạo, người này đăng nhập bằng SĐT + OTP như bình thường; vai trò lấy từ CSDL,
không lấy từ dữ liệu client gửi lên.
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.constants import UserRole
from app.core.phone import InvalidPhoneError, normalize_phone
from app.database import SessionFactory
from app.domains.users.models import User


async def create_admin(raw_phone: str, full_name: str) -> int:
    try:
        phone = normalize_phone(raw_phone)
    except InvalidPhoneError as exc:
        print(f"Lỗi: {exc}")
        return 1

    async with SessionFactory() as db:
        existing = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
        if existing is not None:
            if existing.role is UserRole.ADMIN:
                print(f"{phone} đã là quản trị viên rồi.")
                return 0
            existing.role = UserRole.ADMIN
            await db.commit()
            print(f"Đã nâng {phone} ({existing.full_name}) lên quản trị viên.")
            return 0

        db.add(User(phone=phone, full_name=full_name, role=UserRole.ADMIN))
        await db.commit()
        print(f"Đã tạo quản trị viên {phone} — {full_name}")
        return 0


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    return asyncio.run(create_admin(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
