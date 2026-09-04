"""Kho lưu tệp đính kèm: URL ký hạn để tải lên và tải xuống (P2-12).

Ảnh trong chat gồm ảnh hiện trường tai nạn, ảnh biên lai, ảnh giấy tờ — nghĩa là dữ liệu cá
nhân. Ba quyết định vì thế:

1. **Không có URL cố định.** Mỗi lần xem sinh một URL ký hạn 15 phút. Lưu URL công khai vào
   DB là tự mở kho ảnh giấy tờ cho cả internet, và một khi link rò ra thì không thu về được.

2. **Tải lên đi thẳng lên kho, không qua backend.** Ảnh 5MB đi qua tiến trình API là chiếm
   worker suốt thời gian truyền, đúng lúc mạng của người gửi đang chậm.

3. **Khoá đối tượng do SERVER sinh**, không nhận từ client. Cho client đặt tên khoá là cho
   phép ghi đè tệp của người khác chỉ bằng cách đoán tên.

Bản mock ở đây ký bằng HMAC của `JWT_SECRET` và trả URL trỏ về chính backend, để dev và test
chạy được mà không cần S3. Đổi sang S3 thật là thay lớp cài đặt, không đổi chỗ gọi.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import get_settings


@dataclass
class PresignedUpload:
    storage_key: str
    upload_url: str
    expires_at: datetime
    max_bytes: int


class StorageProvider(ABC):
    @abstractmethod
    def build_key(self, *, conversation_id: uuid.UUID, content_type: str) -> str: ...

    @abstractmethod
    def presigned_put(self, key: str, *, content_type: str, max_bytes: int) -> PresignedUpload: ...

    @abstractmethod
    def presigned_get(self, key: str) -> str: ...


def _sign(payload: str) -> str:
    return hmac.new(
        get_settings().JWT_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]


class MockStorageProvider(StorageProvider):
    """Bản dùng cho dev/test. URL vẫn có chữ ký và hạn dùng thật, chỉ là kho thì giả."""

    def __init__(self, base_url: str = "https://storage.local/goan") -> None:
        self.base_url = base_url.rstrip("/")

    def build_key(self, *, conversation_id: uuid.UUID, content_type: str) -> str:
        # Ngày trong khoá để job dọn dữ liệu quá hạn lưu trữ (P2-20) quét theo tiền tố được,
        # không phải đọc từng dòng DB.
        ngay = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        duoi = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(
            content_type, "bin"
        )
        return f"chat/{ngay}/{conversation_id}/{uuid.uuid4().hex}.{duoi}"

    def presigned_put(self, key: str, *, content_type: str, max_bytes: int) -> PresignedUpload:
        settings = get_settings()
        het_han = datetime.now(timezone.utc) + timedelta(
            seconds=settings.ATTACHMENT_URL_TTL_SECONDS
        )
        moc = int(het_han.timestamp())
        chu_ky = _sign(f"PUT:{key}:{moc}:{content_type}:{max_bytes}")
        return PresignedUpload(
            storage_key=key,
            upload_url=f"{self.base_url}/{key}?X-Expires={moc}&X-Signature={chu_ky}",
            expires_at=het_han,
            max_bytes=max_bytes,
        )

    def presigned_get(self, key: str) -> str:
        settings = get_settings()
        moc = int(
            (
                datetime.now(timezone.utc) + timedelta(seconds=settings.ATTACHMENT_URL_TTL_SECONDS)
            ).timestamp()
        )
        return f"{self.base_url}/{key}?X-Expires={moc}&X-Signature={_sign(f'GET:{key}:{moc}')}"


_provider: StorageProvider = MockStorageProvider()


def get_storage() -> StorageProvider:
    return _provider


def set_storage(provider: StorageProvider) -> None:
    """Điểm thay thế khi lắp S3 thật, và là chỗ test cắm bản giả vào."""
    global _provider
    _provider = provider
