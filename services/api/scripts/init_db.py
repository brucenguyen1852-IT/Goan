"""Tạo schema trực tiếp từ metadata — CHỈ dùng cho môi trường dev/thử API (vd: SQLite).

Production dùng `alembic upgrade head` trên PostgreSQL + PostGIS.

Chạy: python -m scripts.init_db
"""

import asyncio

from app.config import settings
from app.database import engine
from app.models_registry import Base


async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print(f"Đã tạo {len(Base.metadata.tables)} bảng trên {settings.DATABASE_URL}")


if __name__ == "__main__":
    asyncio.run(init())
