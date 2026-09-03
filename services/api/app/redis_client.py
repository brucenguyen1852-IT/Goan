"""Redis connection pool dùng chung: cache OTP, Redis Geo cho matching, pub/sub cho WebSocket."""

from redis.asyncio import ConnectionPool, Redis

from app.config import settings

_pool = ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)

# Key namespace tập trung để tránh trùng key giữa các domain.
DRIVER_GEO_KEY = "driver_locations"
OTP_KEY = "otp:{phone}"
TRIP_LOCK_KEY = "trip:{trip_id}:lock"
TRIP_OFFER_KEY = "trip:{trip_id}:offers"
TRIP_EVENTS_CHANNEL = "trip:{trip_id}:events"
USER_EVENTS_CHANNEL = "user:{user_id}:events"
RATE_LIMIT_KEY = "ratelimit:{scope}"  # sorted set cửa sổ trượt, xem core/middleware.py


def get_redis() -> Redis:
    """Trả về client dùng chung pool. Không đóng ở caller — pool được quản lý ở lifespan."""
    return Redis(connection_pool=_pool)


async def close_redis() -> None:
    await _pool.disconnect()
