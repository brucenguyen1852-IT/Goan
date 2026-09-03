"""JWT + hashing + mã hoá CCCD at-rest (SPEC 13)."""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.exceptions import UnauthorizedError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def _create_token(subject: str, role: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, role: str) -> str:
    return _create_token(
        subject, role, ACCESS_TOKEN, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: str, role: str) -> str:
    return _create_token(
        subject, role, REFRESH_TOKEN, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, *, expected_type: str = ACCESS_TOKEN) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Token không hợp lệ hoặc đã hết hạn") from exc
    if payload.get("type") != expected_type:
        raise UnauthorizedError("Sai loại token")
    return payload


def generate_qr_token() -> str:
    """QR động của tài xế, đổi mỗi phiên online (SPEC 7.1)."""
    return secrets.token_urlsafe(24)


def generate_otp(length: int | None = None) -> str:
    n = length or settings.OTP_LENGTH
    return "".join(secrets.choice("0123456789") for _ in range(n))


# --- Mã hoá CCCD at-rest ---------------------------------------------------
# MVP dùng XOR-with-HMAC-keystream (deterministic, đủ để không lưu plaintext và
# vẫn tra cứu được). Production nên chuyển sang pgcrypto hoặc KMS envelope encryption.


def _keystream(nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    key = settings.NATIONAL_ID_ENCRYPTION_KEY.encode()
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def encrypt_national_id(value: str) -> str:
    raw = value.encode()
    nonce = hashlib.sha256(raw + settings.NATIONAL_ID_ENCRYPTION_KEY.encode()).digest()[:8]
    cipher = bytes(a ^ b for a, b in zip(raw, _keystream(nonce, len(raw)), strict=True))
    return base64.urlsafe_b64encode(nonce + cipher).decode()


def decrypt_national_id(token: str) -> str:
    blob = base64.urlsafe_b64decode(token.encode())
    nonce, cipher = blob[:8], blob[8:]
    return bytes(
        a ^ b for a, b in zip(cipher, _keystream(nonce, len(cipher)), strict=True)
    ).decode()


def mask_national_id(value: str | None) -> str | None:
    """Chỉ hiển thị 4 số cuối, không bao giờ log plaintext."""
    if not value:
        return None
    return "*" * max(0, len(value) - 4) + value[-4:]
