"""Đăng ký / gỡ thiết bị nhận push (P2-13)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.domains.notifications import service
from app.domains.notifications.schemas import PushTokenOut, RegisterPushTokenRequest
from app.domains.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/devices", response_model=PushTokenOut, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: RegisterPushTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PushTokenOut:
    """Đăng ký token thiết bị. Gửi lại cùng token thì cập nhật, không tạo dòng thứ hai."""
    row = await service.register_push_token(db, user, token=body.token, platform=body.platform)
    return PushTokenOut.model_validate(row)


@router.delete("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    body: RegisterPushTokenRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    """Đăng xuất thì gỡ token của MÁY NÀY, không đụng tới các máy khác của cùng người."""
    await service.revoke_push_token(db, body.token)
