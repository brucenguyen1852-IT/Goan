"""Console xem hồ sơ người dùng — che PII mặc định (phân định §2.3).

Endpoint đọc thường trả về dữ liệu ĐÃ CHE. Muốn xem đầy đủ phải gọi endpoint riêng, có quyền
`pii:full:read`, và **bắt buộc nêu lý do**. Lý do được ghi vào `audit_logs.reason`.
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pii import mask_phone
from app.core.security import decrypt_national_id, mask_national_id
from app.database import get_db
from app.deps import require_permission
from app.domains.iam.models import StaffUser
from app.domains.users.models import User

router = APIRouter(prefix="/ops/users", tags=["ops-users"])


class OpsUserOut(BaseModel):
    """Cái Console thấy mặc định: đủ để làm việc, không đủ để mang ra ngoài."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_masked: str | None
    national_id_masked: str | None
    national_id_verified: bool
    role: str
    status: str


class RevealPiiRequest(BaseModel):
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Vì sao cần xem đầy đủ. Được ghi vĩnh viễn vào nhật ký thao tác.",
    )


class RevealPiiResponse(BaseModel):
    id: uuid.UUID
    phone: str
    national_id_number: str | None


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Không tìm thấy người dùng")
    return user


@router.get("/{user_id}", response_model=OpsUserOut)
async def read_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("user:profile:read")),
) -> OpsUserOut:
    user = await _get_user(db, user_id)
    return OpsUserOut(
        id=user.id,
        full_name=user.full_name,
        phone_masked=mask_phone(user.phone),
        national_id_masked=mask_national_id(
            decrypt_national_id(user.national_id_number) if user.national_id_number else None
        ),
        national_id_verified=user.national_id_verified,
        role=user.role.value,
        status=user.status.value,
    )


# POST chứ không phải GET: hành động này để lại hậu quả (một dòng audit vĩnh viễn) và mang
# theo body bắt buộc. GET có lý do nằm ở query string sẽ trôi vào log của proxy và lịch sử trình duyệt.
@router.post("/{user_id}/reveal-pii", response_model=RevealPiiResponse)
async def reveal_pii(
    user_id: uuid.UUID,
    body: RevealPiiRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("pii:full:read")),
) -> RevealPiiResponse:
    """Xem số điện thoại và CCCD đầy đủ. Mỗi lần gọi là một dòng audit kèm lý do.

    `AuditMiddleware` lấy `reason` từ body và ghi vào `audit_logs.reason` — không cần ghi thêm
    ở đây, ghi hai lần chỉ làm nhật ký khó đọc.
    """
    user = await _get_user(db, user_id)
    return RevealPiiResponse(
        id=user.id,
        phone=user.phone,
        national_id_number=(
            decrypt_national_id(user.national_id_number) if user.national_id_number else None
        ),
    )
