"""Nạp danh mục quyền + 12 vai trò, và tạo tài khoản nội bộ đầu tiên.

    python -m scripts.seed_iam                                  # chỉ nạp vai trò/quyền
    python -m scripts.seed_iam admin@goan.vn "Nguyễn Văn A"      # + tạo super_admin

Chạy lại nhiều lần không sao: chỉ bổ sung thứ còn thiếu, không ghi đè quyền mà người vận hành
đã tự chỉnh từ Console.

Mật khẩu sinh ngẫu nhiên và URI TOTP chỉ in ra MỘT LẦN ở đây. Không có endpoint nào đọc lại
được bí mật TOTP — đọc lại được nghĩa là chiếm được một tài khoản admin là vượt được 2FA của
tất cả mọi người.
"""

import asyncio
import secrets
import sys

from app.database import SessionFactory
from app.domains.iam import service


async def main() -> None:
    async with SessionFactory() as db:
        added = await service.sync_catalog(db)
        print(
            f"Danh mục: +{added['permissions']} quyền, +{added['roles']} vai trò, "
            f"+{added['role_permissions']} liên kết vai trò-quyền"
        )

        if len(sys.argv) < 3:
            print("Chưa tạo tài khoản nào. Cú pháp: python -m scripts.seed_iam <email> <họ tên>")
            return

        email, full_name = sys.argv[1], sys.argv[2]
        if await service.get_by_email(db, email) is not None:
            print(f"Tài khoản {email} đã tồn tại — bỏ qua.")
            return

        password = secrets.token_urlsafe(16)
        staff, uri = await service.create_staff(
            db, email=email, full_name=full_name, password=password, role_codes=["super_admin"]
        )
        print("\n=== TÀI KHOẢN NỘI BỘ ĐẦU TIÊN — CHỈ HIỆN MỘT LẦN ===")
        print(f"  Email     : {staff.email}")
        print(f"  Mật khẩu  : {password}")
        print(f"  TOTP URI  : {uri}")
        print("  Quét URI trên vào Google Authenticator/1Password rồi đổi mật khẩu ngay.\n")


if __name__ == "__main__":
    asyncio.run(main())
