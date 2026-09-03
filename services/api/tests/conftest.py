"""Fixture dùng chung: DB SQLite in-memory (async) + factory tạo rider/driver/trip."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.constants import OnlineStatus, TripStatus, UserRole
from app.domains.trips.models import Trip
from app.domains.users.models import DriverProfile, User
from app.models_registry import Base
from tests.fakes import FakeRedis


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest_asyncio.fixture
async def api_client(db, fake_redis, monkeypatch):
    """HTTP client chạy qua đúng chuỗi middleware thật (RequestId -> RateLimit -> Idempotency -> Audit).

    Đây là điểm khác biệt so với test service: nó bắt được lỗi ở tầng middleware, thứ mà
    test gọi thẳng hàm không bao giờ thấy.
    """
    import app.core.audit_middleware as audit_mw
    import app.core.idempotency as idem
    import app.core.middleware as rate_mw
    from app.database import get_db
    from app.deps import get_redis
    from app.main import app

    monkeypatch.setattr(rate_mw, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(idem, "get_redis", lambda: fake_redis)

    class _SessionCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(audit_mw, "SessionFactory", lambda: _SessionCtx())

    async def _get_db():
        yield db

    async def _get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_redis] = _get_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def create_rider(db, *, phone: str = "0900000001") -> User:
    user = User(phone=phone, full_name="Khách Test", role=UserRole.RIDER)
    db.add(user)
    await db.commit()
    return user


async def create_driver(
    db,
    *,
    phone: str = "0900000002",
    escrow_balance: Decimal = Decimal("0"),
    qr_token: str = "qr-token-test",
    online: bool = True,
) -> tuple[User, DriverProfile]:
    user = User(phone=phone, full_name="Tài Xế Test", role=UserRole.DRIVER)
    db.add(user)
    await db.flush()
    profile = DriverProfile(
        user_id=user.id,
        license_number="B2-123456",
        ekyc_selfie_reference_url="https://cdn.test/selfie-ref.jpg",
        escrow_balance=escrow_balance,
        online_status=OnlineStatus.ONLINE if online else OnlineStatus.OFFLINE,
        active_qr_token=qr_token,
        current_lat=10.776,
        current_lng=106.700,
    )
    db.add(profile)
    await db.commit()
    return user, profile


async def create_trip(
    db,
    rider: User,
    driver: User | None = None,
    *,
    status: TripStatus = TripStatus.DRIVER_ARRIVING,
    optimal_distance_km: Decimal = Decimal("10.00"),
    started_at: datetime | None = None,
    qr_verified: bool = False,
) -> Trip:
    trip = Trip(
        rider_id=rider.id,
        driver_id=driver.id if driver else None,
        status=status,
        pickup_lat=10.776,
        pickup_lng=106.700,
        dropoff_lat=10.800,
        dropoff_lng=106.660,
        optimal_distance_km=optimal_distance_km,
        distance_km=optimal_distance_km,
        duration_minutes=30,
        requested_at=datetime.now(timezone.utc),
        matched_at=datetime.now(timezone.utc),
        started_at=started_at,
        qr_verified_at=datetime.now(timezone.utc) if qr_verified else None,
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(trip)
    await db.commit()
    return trip
