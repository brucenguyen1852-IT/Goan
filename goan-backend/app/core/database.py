from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    """Base class dùng chung cho toàn bộ ORM models."""


def get_db() -> Generator:
    """FastAPI dependency: mở 1 DB session cho mỗi request, đóng lại sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
