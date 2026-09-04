"""Cấu hình toàn hệ thống, đọc từ .env qua pydantic-settings.

Mọi con số nghiệp vụ (biểu giá, take-rate, ký quỹ, ngưỡng gian lận) đều nằm ở đây
hoặc trong `domains/pricing/constants.py` để admin chỉnh được, không rải rác trong code.
"""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "GoAn Backend"
    ENV: str = "dev"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    LOCAL_TZ: str = "Asia/Ho_Chi_Minh"

    # --- Hạ tầng ---
    DATABASE_URL: str = "postgresql+asyncpg://goan:goan@localhost:5432/goan"
    DB_ECHO: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- Auth ---
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = (
        15  # ngắn để giảm thiệt hại khi token bị lộ; client tự refresh
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    OTP_TTL_SECONDS: int = 300
    OTP_LENGTH: int = 6
    OTP_MAX_ATTEMPTS: int = 5
    # Hạn mức theo SỐ ĐIỆN THOẠI — đây mới là thứ gắn với chi phí SMS thật.
    # Hạn mức theo IP (core/middleware.py) chỉ để chặn quét hàng loạt, phải nới rộng vì
    # nhà mạng VN dùng NAT quy mô lớn.
    OTP_MAX_PER_PHONE_WINDOW: int = 3
    OTP_PHONE_WINDOW_SECONDS: int = 300
    OTP_MAX_PER_PHONE_DAY: int = 10

    # --- Đăng nhập nội bộ (Console) ---
    # Phiên 8 giờ = một ca làm việc. Hết ca phải đăng nhập lại kèm 2FA.
    STAFF_SESSION_HOURS: int = 8
    STAFF_MAX_FAILED_ATTEMPTS: int = 5
    STAFF_LOCKOUT_MINUTES: int = 15
    # Nhớ thiết bị đã qua 2FA. Gõ mã 6 số mỗi ca làm việc thì người ta sẽ tìm cách lách,
    # thường là dán mã dự phòng lên màn hình.
    STAFF_TRUSTED_DEVICE_DAYS: int = 30
    # Đề nghị chạm tiền treo quá lâu rồi được duyệt trong bối cảnh đã khác là cách tạo
    # ra sai sót đắt tiền. 72 giờ = 3 ngày làm việc.
    APPROVAL_EXPIRE_HOURS: int = 72
    # Nhịp đẩy ảnh chụp đội xe cho Console. Ngắn hơn thì điều phối viên không đọc kịp,
    # dài hơn thì bản đồ trông như bị treo.
    OPS_FLEET_PUSH_SECONDS: float = 3.0

    # --- Hỗ trợ khách hàng (phân định §7.5) ---
    # Hạn phản hồi ĐẦU TIÊN theo mức ưu tiên, tính bằng phút. Quá hạn thì ticket tự leo thang
    # lên cs_lead — con số này là cam kết vận hành, nên để ở đây cho sửa được mà không deploy.
    SLA_FIRST_RESPONSE_MINUTES: dict[str, int] = {
        "urgent": 2,  # an toàn, tai nạn
        "high": 15,  # dính tiền
        "normal": 60,
        "low": 480,
    }
    # Agent tắt máy giữa ca thì ticket của họ phải quay về hàng đợi, không nằm chờ hết ngày.
    AGENT_OFFLINE_RELEASE_MINUTES: int = 10
    # Trần số hội thoại một agent ôm cùng lúc. Vượt trần thì phân cho người khác.
    AGENT_DEFAULT_MAX_CHATS: int = 5

    # --- Tệp đính kèm trong chat (P2-12) ---
    # 5MB: đủ cho một ảnh chụp hiện trường bằng điện thoại, chặn trước khi ai đó gửi video.
    ATTACHMENT_MAX_BYTES: int = 5 * 1024 * 1024
    # URL đọc ảnh chỉ sống 15 phút. Link rò ra thì cũng chỉ rò trong 15 phút.
    ATTACHMENT_URL_TTL_SECONDS: int = 900
    ATTACHMENT_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]

    # --- Push (P2-13) ---
    # Chờ vài giây rồi mới push: người đang mở app đã thấy tin qua WebSocket từ lâu, và bắn
    # thêm thông báo cho tin họ vừa đọc là cách làm người ta tắt thông báo của ứng dụng.
    PUSH_ON_MESSAGE_DELAY_SECONDS: int = 5
    # Tắt trong test: ở đó không có broker, và bài test về push gọi thẳng hàm xử lý.
    PUSH_ON_MESSAGE_ENABLED: bool = True

    # --- Hạn lưu trữ hội thoại (phân định §7.6) — P2-20 ---
    # Chat chuyến giữ 12 tháng; chat hỗ trợ giữ 24 tháng vì nó là BẰNG CHỨNG khiếu nại và
    # khiếu nại đến muộn. Quá hạn thì ẩn danh hoá, không xoá dòng: xoá là mất cả số liệu
    # thống kê lẫn khả năng chứng minh cuộc trò chuyện đó từng tồn tại.
    CHAT_RETENTION_MONTHS_TRIP: int = 12
    CHAT_RETENTION_MONTHS_SUPPORT: int = 24

    # --- Phân bổ doanh thu (SPEC 4.4) ---
    DRIVER_SHARE_RATE: Decimal = Decimal("0.58")  # tài xế nhận ~58% cước (chưa gồm phụ thu đón xa)
    TAKE_RATE: Decimal = Decimal("0.38")  # take-rate nền tảng Năm 1 = 38%
    PAYMENT_GATEWAY_FEE_RATE: Decimal = Decimal("0.02")  # ~2%, trừ trong phần nền tảng giữ
    INSURANCE_FEE_RATE: Decimal = Decimal("0.06")  # 5-8% (SPEC 10.3), trừ trong phần nền tảng giữ

    # --- Phụ thu đón xa (SPEC 4.3) ---
    PICKUP_FREE_RADIUS_KM: Decimal = Decimal("5")
    PICKUP_SURCHARGE_AMOUNT: Decimal = Decimal("20000")

    # --- Ký quỹ (SPEC 8) ---
    ESCROW_ACCRUAL_RATE: Decimal = Decimal("0.15")  # 15% của driver_payout
    ESCROW_DEFAULT_TARGET: Decimal = Decimal("3000000")  # 3 triệu, range 3-5 triệu
    ESCROW_REFUND_DELAY_DAYS: int = 45  # 45-60 ngày

    # --- Matching (SPEC 6) ---
    MATCHING_RADIUS_STEPS_KM: list[int] = [5, 8, 12]
    MATCHING_OFFER_FANOUT: int = 5  # số tài xế được broadcast đồng thời
    MATCHING_TIMEOUT_SECONDS: int = 90
    MATCHING_OFFER_TTL_SECONDS: int = 20
    NEW_ZONE_SUBSIDY_AMOUNT: Decimal = Decimal(
        "20000"
    )  # trợ cấp vùng mới, lấy từ ngân sách marketing

    # --- Chống gian lận (SPEC 7) ---
    ROUTE_DEVIATION_FACTOR: Decimal = Decimal("1.5")
    ROUTE_DEVIATION_PENALTY_MULTIPLIER: Decimal = Decimal("2")
    FRAUD_STRIKE_LOCK_THRESHOLD: int = 3
    SELFIE_MATCH_THRESHOLD: float = 0.85
    SELFIE_CHECK_MIN_INTERVAL_MINUTES: int = 30
    SELFIE_CHECK_MAX_INTERVAL_MINUTES: int = 90

    # --- Chuyến đi / ví ---
    CANCELLATION_GRACE_MINUTES: int = 5
    CANCELLATION_FEE: Decimal = Decimal("20000")
    WALLET_HOLD_HOURS: int = 24  # pending_balance -> available_balance
    TRIP_COMPLETE_RADIUS_M: int = 300  # tài xế phải ở gần điểm đến khi bấm kết thúc

    # --- Hardening ---
    RATE_LIMIT_PER_MINUTE: int = 120
    JSON_LOGS: bool = True

    # --- Quan sát hệ thống ---
    SENTRY_DSN: str = ""  # trống = tắt, không cần cài sentry-sdk ở dev
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    RELEASE: str = ""
    # Trace phân tán. Trống = tắt; gói OTel nằm ở requirements-observability.txt.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "goan-api"
    OTEL_TRACES_SAMPLE_RATE: float = 0.1
    # Số liệu Prometheus ở /metrics. Đặt METRICS_TOKEN ở production để chỉ Prometheus scrape
    # được — /metrics phơi bày đường dẫn và tần suất gọi, không nên để công khai.
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""

    # --- Idempotency ---
    IDEMPOTENCY_TTL_SECONDS: int = 86400  # giữ kết quả 24h
    IDEMPOTENCY_REQUIRED: bool = False  # bật khi mọi client đã gửi header (xem docs/QA)

    # --- Audit ---
    AUDIT_ENABLED: bool = True

    # --- Mã hoá CCCD at-rest (SPEC 13) ---
    NATIONAL_ID_ENCRYPTION_KEY: str = "dev-only-32-bytes-key-change-me!"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
