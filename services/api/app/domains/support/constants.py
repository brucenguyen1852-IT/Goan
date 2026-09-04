"""Hằng số cho ticket hỗ trợ (tài liệu phân định §7.2, §7.5) — P2-08…P2-10."""

from enum import Enum


class TicketCategory(str, Enum):
    PAYMENT = "payment"
    FRAUD = "fraud"
    SAFETY = "safety"
    APP_ISSUE = "app_issue"
    DRIVER_CONDUCT = "driver_conduct"
    RIDER_CONDUCT = "rider_conduct"
    OTHER = "other"


class TicketPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, Enum):
    NEW = "new"
    ASSIGNED = "assigned"
    WAITING_CUSTOMER = "waiting_customer"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketTeam(str, Enum):
    CS = "cs"
    RISK = "risk"
    FINANCE = "finance"
    DRIVER_OPS = "driver_ops"


class SubjectType(str, Enum):
    RIDER = "rider"
    DRIVER = "driver"


class AgentStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"


class TicketEventType(str, Enum):
    CREATED = "created"
    ASSIGNED = "assigned"
    FIRST_RESPONSE = "first_response"
    TRANSFERRED = "transferred"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    RELEASED = "released"  # agent offline quá lâu, ticket quay về hàng đợi


# Trạng thái coi như "đang mở" — chưa kết luận, vẫn tính vào tải của agent và vào SLA.
OPEN_TICKET_STATUSES = (
    TicketStatus.NEW,
    TicketStatus.ASSIGNED,
    TicketStatus.WAITING_CUSTOMER,
    TicketStatus.ESCALATED,
)

# Trạng thái đã chốt: không tính tải, không đếm SLA nữa.
CLOSED_TICKET_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)

# Đội xử lý mặc định theo loại vấn đề. Ghi ở đây chứ không rải if-else trong service: đổi
# phân công là đổi một dòng, và đọc bảng này biết ngay ai chịu trách nhiệm việc gì.
DEFAULT_TEAM: dict[TicketCategory, TicketTeam] = {
    TicketCategory.PAYMENT: TicketTeam.FINANCE,
    TicketCategory.FRAUD: TicketTeam.RISK,
    TicketCategory.SAFETY: TicketTeam.CS,
    TicketCategory.APP_ISSUE: TicketTeam.CS,
    TicketCategory.DRIVER_CONDUCT: TicketTeam.DRIVER_OPS,
    TicketCategory.RIDER_CONDUCT: TicketTeam.CS,
    TicketCategory.OTHER: TicketTeam.CS,
}

# Mức ưu tiên tối thiểu theo loại vấn đề. Khách tự chọn "thấp" cho một vụ tai nạn cũng không
# làm nó thành việc thấp — an toàn và tiền luôn được nâng lên, không bao giờ hạ xuống.
MIN_PRIORITY: dict[TicketCategory, TicketPriority] = {
    TicketCategory.SAFETY: TicketPriority.URGENT,
    TicketCategory.FRAUD: TicketPriority.HIGH,
    TicketCategory.PAYMENT: TicketPriority.HIGH,
}

PRIORITY_ORDER: tuple[TicketPriority, ...] = (
    TicketPriority.LOW,
    TicketPriority.NORMAL,
    TicketPriority.HIGH,
    TicketPriority.URGENT,
)
