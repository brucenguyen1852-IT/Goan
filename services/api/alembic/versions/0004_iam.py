"""IAM nội bộ: staff_users, roles, permissions, role_permissions, staff_roles

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_roles_code", "roles", ["code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "permission_id",
            sa.Uuid(),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    op.create_table(
        "staff_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
        sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_reason", sa.Text(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_staff_users_email", "staff_users", ["email"], unique=True)

    op.create_table(
        "staff_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "staff_user_id",
            sa.Uuid(),
            sa.ForeignKey("staff_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.UniqueConstraint("staff_user_id", "role_id", name="uq_staff_role"),
    )
    op.create_index("ix_staff_roles_staff_user_id", "staff_roles", ["staff_user_id"])
    op.create_index("ix_staff_roles_role_id", "staff_roles", ["role_id"])

    # Thao tác của nhân sự nội bộ không dùng chung khoá ngoại với users.
    op.add_column("audit_logs", sa.Column("actor_staff_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_audit_logs_actor_staff",
        "audit_logs",
        "staff_users",
        ["actor_staff_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audit_logs_staff_created", "audit_logs", ["actor_staff_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_staff_created", table_name="audit_logs")
    op.drop_constraint("fk_audit_logs_actor_staff", "audit_logs", type_="foreignkey")
    op.drop_column("audit_logs", "actor_staff_id")

    op.drop_index("ix_staff_roles_role_id", table_name="staff_roles")
    op.drop_index("ix_staff_roles_staff_user_id", table_name="staff_roles")
    op.drop_table("staff_roles")

    op.drop_index("ix_staff_users_email", table_name="staff_users")
    op.drop_table("staff_users")

    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index("ix_roles_code", table_name="roles")
    op.drop_table("roles")

    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
