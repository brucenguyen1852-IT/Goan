"""Push notification (FCM / APNs) — interface chuẩn + bản mock cho MVP (P2-13).

Push là kênh DUY NHẤT tới được người dùng khi app đã đóng, nên nó quyết định "tin nhắn tới
máy trong 5 giây" có thật hay không. Ba ràng buộc:

1. **Lỗi push không được làm hỏng việc đã xong.** Tin nhắn đã ghi vào DB rồi; FCM chết thì
   người dùng nhận muộn, chứ không được mất tin.
2. **Token chết phải bị gỡ.** Cài lại app là token cũ vô hiệu vĩnh viễn; giữ lại thì mỗi tin
   nhắn tốn thêm một lời gọi mạng chắc chắn thất bại, nhân với số người dùng cũ.
3. **Không nhét nội dung nhạy cảm vào payload.** Thông báo hiện trên màn hình khoá, người
   ngồi cạnh cũng đọc được.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.logging import log_event

logger = logging.getLogger("goan.push")


@dataclass
class PushResult:
    delivered: int
    invalid_tokens: list[str] = field(default_factory=list)


class PushProvider(ABC):
    @abstractmethod
    async def send(
        self, tokens: list[str], *, title: str, body: str, data: dict[str, str] | None = None
    ) -> PushResult: ...


class MockPushProvider(PushProvider):
    """Bản dev/test: ghi log và nhớ lại những gì đã gửi.

    Quy ước test: token bắt đầu bằng `invalid-` được coi là token chết, để luồng gỡ token
    hỏng có đường chạy thật chứ không chỉ là mã chưa bao giờ được thực thi.
    """

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(
        self, tokens: list[str], *, title: str, body: str, data: dict[str, str] | None = None
    ) -> PushResult:
        hong = [t for t in tokens if t.startswith("invalid-")]
        song = [t for t in tokens if t not in hong]
        self.sent.append({"tokens": song, "title": title, "body": body, "data": data or {}})
        log_event(logger, "push_sent", count=len(song), title=title)
        return PushResult(delivered=len(song), invalid_tokens=hong)


_provider: PushProvider = MockPushProvider()


def get_push() -> PushProvider:
    return _provider


def set_push(provider: PushProvider) -> None:
    """Điểm thay thế khi lắp FCM thật, và là chỗ test cắm bản giả vào."""
    global _provider
    _provider = provider
