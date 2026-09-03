"""Seed dữ liệu mẫu tối thiểu để test end-to-end: 2 rider + 3 driver + 1 partner (SPEC 12).

Chạy: python -m scripts.seed
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.constants import (
    DriverApprovalStatus,
    EscrowStatus,
    OnlineStatus,
    PartnerType,
    TimeBand,
    UserRole,
)
from app.core.security import generate_qr_token
from app.database import SessionFactory
from app.domains.partners.models import Partner, SatelliteZone
from app.domains.pricing.constants import DEFAULT_FARE_RULES
from app.domains.pricing.models import PricingRule
from app.domains.users.models import DriverProfile, User

RIDERS = [
    ("0901000001", "Nguyễn Văn Khách"),
    ("0901000002", "Trần Thị Khách"),
]
DRIVERS = [
    ("0902000001", "Lê Văn Tài", Decimal("0"), (10.7769, 106.7009)),
    ("0902000002", "Phạm Văn Xế", Decimal("1500000"), (10.7800, 106.6950)),
    ("0902000003", "Đỗ Văn Lái", Decimal("3000000"), (10.7700, 106.7100)),
]


async def seed() -> None:
    async with SessionFactory() as db:
        for phone, name in RIDERS:
            if await _exists(db, phone):
                continue
            db.add(User(phone=phone, full_name=name, role=UserRole.RIDER))

        for phone, name, escrow, (lat, lng) in DRIVERS:
            if await _exists(db, phone):
                continue
            user = User(phone=phone, full_name=name, role=UserRole.DRIVER)
            db.add(user)
            await db.flush()
            db.add(
                DriverProfile(
                    user_id=user.id,
                    license_number=f"B2-{phone[-6:]}",
                    # Tài xế mẫu coi như đã qua bước duyệt hồ sơ của Driver Ops (P1-10),
                    # để smoke test và bản demo chạy được ngay.
                    approval_status=DriverApprovalStatus.APPROVED,
                    license_years_experience=5,
                    ekyc_selfie_reference_url="https://cdn.goan.vn/seed/selfie.jpg",
                    escrow_balance=escrow,
                    escrow_status=(
                        EscrowStatus.FULFILLED
                        if escrow >= Decimal("3000000")
                        else EscrowStatus.ACCUMULATING
                    ),
                    online_status=OnlineStatus.ONLINE,
                    active_qr_token=generate_qr_token(),
                    current_lat=lat,
                    current_lng=lng,
                )
            )

        if not (await db.execute(select(Partner).limit(1))).first():
            restaurant = Partner(
                type=PartnerType.RESTAURANT,
                name="Quán Nhậu Bình Minh",
                commission_rate=Decimal("5.00"),
                qr_code_token="goan-restaurant-demo",
                lat=10.7765,
                lng=106.7005,
                address="12 Nguyễn Huệ, Q1, TP.HCM",
                contact_info={"phone": "02838000000"},
            )
            db.add(restaurant)
            db.add(
                Partner(
                    type=PartnerType.INSURANCE,
                    name="Bảo hiểm GoAn Care",
                    commission_rate=Decimal("6.00"),
                    contact_info={"phone": "19001000"},
                )
            )
            await db.flush()
            db.add(
                SatelliteZone(
                    partner_id=restaurant.id,
                    name="Khu Bùi Viện",
                    lat=10.7670,
                    lng=106.6930,
                    radius_m=1200,
                    is_new_zone=True,
                    active_hours={"start": "19:00", "end": "02:00"},
                )
            )

        if not (await db.execute(select(PricingRule).limit(1))).first():
            now = datetime.now(timezone.utc)
            for band in (TimeBand.NORMAL, TimeBand.NIGHT, TimeBand.PEAK):
                rule = DEFAULT_FARE_RULES[band]
                db.add(
                    PricingRule(
                        time_band=band,
                        base_fee=rule.base_fee,
                        per_km=rule.per_km,
                        per_minute=rule.per_minute,
                        min_fare=rule.min_fare,
                        take_rate=Decimal("0.3800"),
                        driver_share_rate=Decimal("0.5800"),
                        effective_from=now,
                    )
                )

        await db.commit()
        await _push_drivers_to_redis_geo(db)
        print("Seed xong: 2 rider, 3 driver, 2 partner, 1 satellite zone, 3 pricing rule")


async def _push_drivers_to_redis_geo(db) -> None:
    """Đưa tài xế seed vào Redis GEO để matching tìm thấy ngay mà không cần gọi /drivers/me/online."""
    from app.redis_client import DRIVER_GEO_KEY, get_redis

    stmt = select(DriverProfile).where(DriverProfile.online_status == OnlineStatus.ONLINE)
    profiles = (await db.execute(stmt)).scalars().all()
    try:
        redis = get_redis()
        for p in profiles:
            if p.current_lat is not None and p.current_lng is not None:
                await redis.geoadd(DRIVER_GEO_KEY, (p.current_lng, p.current_lat, str(p.user_id)))
        print(f"Đã nạp {len(profiles)} tài xế vào Redis GEO")
    except Exception as exc:
        print(f"Bỏ qua Redis GEO ({type(exc).__name__}): matching sẽ không tìm thấy tài xế")


async def _exists(db, phone: str) -> bool:
    return (await db.execute(select(User.id).where(User.phone == phone))).first() is not None


if __name__ == "__main__":
    asyncio.run(seed())
