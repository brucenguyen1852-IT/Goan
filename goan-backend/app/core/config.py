from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình ứng dụng, đọc từ biến môi trường / file .env"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "GoAn API"
    APP_ENV: str = "development"
    DEBUG: bool = True

    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALGORITHM: str = "HS256"

    DATABASE_URL: str = "postgresql://goan:goan_password@localhost:5432/goan_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    VNPAY_TMN_CODE: str = ""
    VNPAY_HASH_SECRET: str = ""
    MOMO_PARTNER_CODE: str = ""
    MOMO_ACCESS_KEY: str = ""
    MOMO_SECRET_KEY: str = ""

    EKYC_PROVIDER_API_KEY: str = ""
    EKYC_PROVIDER_BASE_URL: str = ""

    SMS_PROVIDER_API_KEY: str = ""
    SMS_PROVIDER_BASE_URL: str = ""

    MAPS_PROVIDER_API_KEY: str = ""

    # Bảng giá mặc định — nguồn thật vẫn nên là bảng pricing_rules trong DB
    PRICING_BASE_FEE: int = 30_000
    PRICING_MIN_FARE_NORMAL: int = 100_000

    # Tỷ lệ chia sẻ (đúng theo mô hình trong pitch deck)
    PLATFORM_TAKE_RATE: float = 0.38
    DRIVER_SHARE_RATE: float = 0.58
    ESCROW_DEDUCTION_RATE: float = 0.15
    ESCROW_TARGET_AMOUNT: int = 4_000_000
    FAR_PICKUP_THRESHOLD_KM: float = 5.0
    FAR_PICKUP_SURCHARGE: int = 20_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
