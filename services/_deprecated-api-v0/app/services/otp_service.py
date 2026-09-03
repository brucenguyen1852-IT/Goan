"""OTP Service — gửi/xác thực mã OTP qua SMS khi đăng nhập.
Giai đoạn dev: lưu OTP tạm trong Redis với TTL 5 phút, log ra console thay vì gửi SMS thật.
"""

import random
import redis

from app.core.config import settings

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

OTP_TTL_SECONDS = 300


def generate_and_send_otp(phone: str) -> str:
    otp = f"{random.randint(0, 999999):06d}"
    _redis.setex(f"otp:{phone}", OTP_TTL_SECONDS, otp)

    if settings.APP_ENV == "development":
        print(f"[DEV] OTP cho {phone}: {otp}")  # thay bằng gọi SMS_PROVIDER thật ở production
    else:
        # TODO: gọi API nhà cung cấp SMS (ESMS/Speedsms) tại đây
        pass

    return otp


def verify_otp(phone: str, otp_input: str) -> bool:
    stored = _redis.get(f"otp:{phone}")
    if stored is None:
        return False
    if stored == otp_input:
        _redis.delete(f"otp:{phone}")
        return True
    return False
