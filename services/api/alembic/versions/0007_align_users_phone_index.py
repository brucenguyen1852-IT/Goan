"""Gộp ràng buộc duy nhất của users.phone vào đúng một unique index

Revision ID: 0007
Revises: 0006

Migration 0001 tạo CẢ HAI: ràng buộc `users_phone_key` (sinh ra từ `unique=True` trên cột) và
một index thường `ix_users_phone`. Model chỉ mô tả một thứ: `unique=True, index=True`, tức MỘT
unique index. Chênh lệch này làm `alembic check` đỏ mãi, và khi cổng kiểm tra luôn đỏ thì không
ai còn đọc nó nữa — đúng lúc nó cần báo một thay đổi thật thì không ai nghe.

Không đổi hành vi: trước và sau, số điện thoại vẫn là duy nhất.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_constraint("users_phone_key", "users", type_="unique")
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_phone", table_name="users")
    op.create_unique_constraint("users_phone_key", "users", ["phone"])
    op.create_index("ix_users_phone", "users", ["phone"])
