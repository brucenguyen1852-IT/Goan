"""Router Console: đăng nhập nội bộ, quản lý nhân sự, vai trò, đọc nhật ký thao tác.

Router không chứa logic: xác thực → kiểm quyền → đổi DTO → gọi service (tài liệu phân định §3.1).
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    new_jti,
    new_token_family,
)
from app.database import get_db
from app.deps import STAFF_ROLE, get_current_staff, get_redis, require_permission
from app.domains.audit.models import AuditLog
from app.domains.auth import tokens as token_store
from app.domains.iam import service
from app.domains.iam.models import Role, StaffUser
from app.domains.iam.schemas import (
    AuditLogOut,
    AuditLogPage,
    RoleOut,
    StaffCreateRequest,
    StaffCreateResponse,
    StaffDeactivateRequest,
    StaffLoginRequest,
    StaffOut,
    StaffRefreshRequest,
    StaffRolesRequest,
    StaffTokens,
)

router = APIRouter(prefix="/ops", tags=["ops-iam"])

MAX_PAGE_SIZE = 200


def _to_out(staff: StaffUser) -> StaffOut:
    return StaffOut(
        id=staff.id,
        email=staff.email,
        full_name=staff.full_name,
        is_active=staff.is_active,
        roles=sorted(role.code for role in staff.roles),
        permissions=sorted(service.permissions_of(staff)),
        last_login_at=staff.last_login_at,
        locked_until=staff.locked_until,
        deactivated_reason=staff.deactivated_reason,
    )


def _issue_tokens(staff: StaffUser, *, family: str | None = None) -> tuple[StaffTokens, str, str]:
    """Access 15 phút + refresh giới hạn theo phiên 8 giờ. Trả kèm (jti, family) để lưu Redis."""
    fam = family or new_token_family()
    jti = new_jti()
    session = timedelta(hours=settings.STAFF_SESSION_HOURS)
    payload = StaffTokens(
        access_token=create_access_token(str(staff.id), STAFF_ROLE, family=fam),
        refresh_token=create_refresh_token(
            str(staff.id), STAFF_ROLE, jti=jti, family=fam, expires_delta=session
        ),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        session_expires_in=int(session.total_seconds()),
    )
    return payload, jti, fam


# --- Đăng nhập ------------------------------------------------------------------------


@router.post("/auth/login", response_model=StaffTokens)
async def login(
    body: StaffLoginRequest, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)
) -> StaffTokens:
    """Email + mật khẩu + TOTP. Sai 5 lần thì khoá tạm thời."""
    staff = await service.authenticate(
        db, email=body.email, password=body.password, totp_code=body.totp_code
    )
    payload, jti, family = _issue_tokens(staff)
    await token_store.register(redis, jti=jti, family=family)
    return payload


@router.post("/auth/refresh", response_model=StaffTokens)
async def refresh(
    body: StaffRefreshRequest, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)
) -> StaffTokens:
    """Xoay vòng như phía app: token cũ tiêu ngay, dùng lại token đã tiêu là mất cả phiên."""
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if payload.get("role") != STAFF_ROLE:
        raise UnauthorizedError("Sai loại token")
    family = payload.get("fam", "")
    if await token_store.is_family_revoked(redis, family):
        raise UnauthorizedError("Phiên đăng nhập đã bị thu hồi")

    staff = await service.get_by_id(db, uuid.UUID(payload["sub"]))
    if not staff.is_active:
        raise UnauthorizedError("Tài khoản đã bị vô hiệu hoá")
    try:
        await token_store.consume(redis, jti=payload["jti"], family=family, user_id=payload["sub"])
    except token_store.TokenReuseDetected as exc:
        raise UnauthorizedError(str(exc)) from exc

    tokens, jti, fam = _issue_tokens(staff, family=family)
    await token_store.register(redis, jti=jti, family=fam)
    return tokens


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: StaffRefreshRequest, redis=Depends(get_redis)) -> None:
    """Thu hồi cả phiên. Chỉ xoá token ở máy thì phiên vẫn sống tới hết 8 giờ."""
    payload = decode_token(body.refresh_token, expected_type="refresh")
    await token_store.revoke_family(redis, payload.get("fam", ""))


@router.get("/auth/me", response_model=StaffOut)
async def me(staff: StaffUser = Depends(get_current_staff)) -> StaffOut:
    """Console gọi ngay sau khi đăng nhập để biết được hiện những menu nào."""
    return _to_out(staff)


# --- Nhân sự --------------------------------------------------------------------------


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:read")),
) -> list[StaffOut]:
    stmt = select(StaffUser).order_by(StaffUser.created_at.desc())
    if not include_inactive:
        stmt = stmt.where(StaffUser.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(s) for s in rows]


@router.post("/staff", response_model=StaffCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    body: StaffCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:write")),
) -> StaffCreateResponse:
    staff, uri = await service.create_staff(
        db,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role_codes=body.roles,
    )
    return StaffCreateResponse(staff=_to_out(staff), totp_provisioning_uri=uri)


@router.get("/staff/{staff_id}", response_model=StaffOut)
async def get_staff(
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:read")),
) -> StaffOut:
    return _to_out(await service.get_by_id(db, staff_id))


@router.put("/staff/{staff_id}/roles", response_model=StaffOut)
async def set_roles(
    staff_id: uuid.UUID,
    body: StaffRolesRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:write")),
) -> StaffOut:
    staff = await service.get_by_id(db, staff_id)
    return _to_out(await service.set_roles(db, staff, body.roles))


@router.post("/staff/{staff_id}/deactivate", response_model=StaffOut)
async def deactivate_staff(
    staff_id: uuid.UUID,
    body: StaffDeactivateRequest,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:write")),
) -> StaffOut:
    """Vô hiệu hoá chứ không xoá — xoá là mất dấu vết mọi thao tác người đó từng làm."""
    staff = await service.get_by_id(db, staff_id)
    return _to_out(await service.deactivate(db, staff, body.reason))


@router.post("/staff/{staff_id}/reactivate", response_model=StaffOut)
async def reactivate_staff(
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:write")),
) -> StaffOut:
    staff = await service.get_by_id(db, staff_id)
    return _to_out(await service.reactivate(db, staff))


@router.post("/staff/{staff_id}/unlock", response_model=StaffOut)
async def unlock_staff(
    staff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:staff:write")),
) -> StaffOut:
    staff = await service.get_by_id(db, staff_id)
    return _to_out(await service.unlock(db, staff))


# --- Vai trò --------------------------------------------------------------------------


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("iam:role:read")),
) -> list[RoleOut]:
    rows = (await db.execute(select(Role).order_by(Role.code))).scalars().all()
    return [
        RoleOut(code=r.code, name=r.name, permissions=sorted(p.code for p in r.permissions))
        for r in rows
    ]


# --- Nhật ký thao tác -----------------------------------------------------------------


@router.get("/audit-logs", response_model=AuditLogPage)
async def read_audit_logs(
    actor_id: uuid.UUID | None = Query(default=None, description="Lọc theo người dùng app"),
    actor_staff_id: uuid.UUID | None = Query(default=None, description="Lọc theo nhân sự nội bộ"),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    cursor: datetime | None = Query(default=None, description="`next_cursor` của trang trước"),
    db: AsyncSession = Depends(get_db),
    _: StaffUser = Depends(require_permission("audit:log:read")),
) -> AuditLogPage:
    """Phân trang theo con trỏ thời gian, không dùng OFFSET: bảng này chỉ có lớn dần."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit + 1)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if actor_staff_id:
        stmt = stmt.where(AuditLog.actor_staff_id == actor_staff_id)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)
    if cursor:
        stmt = stmt.where(AuditLog.created_at < cursor)

    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1].created_at
        # Kết thúc bằng 'Z' chứ không phải '+00:00': dấu '+' trong query string bị hiểu thành
        # dấu cách, client nào quên mã hoá URL là nhận 422 mà không hiểu vì sao.
        next_cursor = (
            (last if last.tzinfo else last.replace(tzinfo=timezone.utc))
            .isoformat()
            .replace("+00:00", "Z")
        )
    return AuditLogPage(
        items=[AuditLogOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )
