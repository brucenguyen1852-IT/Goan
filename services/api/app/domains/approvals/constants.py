"""Loại đề nghị và cặp quyền maker/checker tương ứng."""

from enum import Enum


class ApprovalKind(str, Enum):
    PAYOUT = "payout"  # chi tiền cho tài xế
    ESCROW_REFUND = "escrow_refund"  # hoàn ký quỹ khi ngưng hợp tác
    FARE_ADJUSTMENT = "fare_adjustment"  # điều chỉnh cước một chuyến
    FRAUD_PENALTY = "fraud_penalty"  # phạt / khoá vì gian lận
    REFUND = "refund"  # hoàn tiền cho khách vượt hạn mức CSKH


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# (quyền để TẠO đề nghị, quyền để DUYỆT). Hai vế phải khác nhau, và theo ma trận vai trò
# trong tài liệu phân định thì không vai trò nào (trừ super_admin) giữ cả hai.
PERMISSION_PAIRS: dict[ApprovalKind, tuple[str, str]] = {
    ApprovalKind.PAYOUT: ("finance:payout:create", "finance:payout:approve"),
    ApprovalKind.ESCROW_REFUND: ("finance:payout:create", "finance:escrow_refund:approve"),
    ApprovalKind.FARE_ADJUSTMENT: ("finance:payout:create", "finance:payout:approve"),
    ApprovalKind.FRAUD_PENALTY: ("risk:penalty:propose", "risk:penalty:approve"),
    ApprovalKind.REFUND: ("support:ticket:write", "support:refund:approve"),
}
