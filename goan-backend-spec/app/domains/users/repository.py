import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import OnlineStatus
from app.domains.users.models import DriverProfile, User


async def get_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    return (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_driver_profile_by_user(db: AsyncSession, user_id: uuid.UUID) -> DriverProfile | None:
    stmt = select(DriverProfile).where(DriverProfile.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_driver_profiles_by_user_ids(
    db: AsyncSession, user_ids: list[uuid.UUID]
) -> list[DriverProfile]:
    if not user_ids:
        return []
    stmt = select(DriverProfile).where(DriverProfile.user_id.in_(user_ids))
    return list((await db.execute(stmt)).scalars().all())


async def list_online_driver_profiles(db: AsyncSession) -> list[DriverProfile]:
    stmt = select(DriverProfile).where(DriverProfile.online_status == OnlineStatus.ONLINE)
    return list((await db.execute(stmt)).scalars().all())
