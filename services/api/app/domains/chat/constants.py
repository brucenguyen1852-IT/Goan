"""Hằng số cho hội thoại (tài liệu phân định §7)."""

from enum import Enum


class ConversationKind(str, Enum):
    TRIP = "trip"  # khách ↔ tài xế trong một chuyến, CSKH có thể tham gia
    SUPPORT = "support"  # khách hoặc tài xế ↔ CSKH
    INTERNAL = "internal"  # nội bộ giữa nhân sự


class ConversationStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class MemberRole(str, Enum):
    RIDER = "rider"
    DRIVER = "driver"
    AGENT = "agent"  # CSKH tham gia hội thoại 3 bên


class MessageKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    SYSTEM = "system"  # "CSKH Minh đã tham gia hội thoại"
