"""Danh mục quyền và 12 vai trò nội bộ (tài liệu phân định §2.3).

Quyền có dạng `domain:action:scope`. Vai trò chỉ là một **tập hợp quyền** lưu trong DB, sửa
được từ Console mà không cần deploy — nên đừng bao giờ viết `if role == "finance_manager"`
trong code nghiệp vụ; hãy hỏi quyền.

Danh mục dưới đây là bản gốc để seed. Sau khi seed, DB là nguồn sự thật: Console thêm/bớt
quyền của một vai trò thì DB đổi, file này không đổi. Chạy lại seed chỉ **bổ sung** quyền
còn thiếu, không xoá thứ người vận hành đã tự thêm.
"""

from __future__ import annotations

# Quyền đặc biệt: khớp mọi quyền khác. Chỉ super_admin được có.
WILDCARD = "*"

# --- Danh mục quyền -------------------------------------------------------------------
PERMISSIONS: dict[str, str] = {
    # Quản trị nhân sự nội bộ
    "iam:staff:read": "Xem danh sách nhân sự nội bộ",
    "iam:staff:write": "Tạo, sửa, vô hiệu hoá nhân sự nội bộ",
    "iam:role:read": "Xem vai trò và ma trận quyền",
    "iam:role:write": "Sửa quyền của vai trò",
    # Dấu vết
    "audit:log:read": "Đọc nhật ký thao tác",
    # Người dùng app
    "user:profile:read": "Xem hồ sơ khách/tài xế (dữ liệu đã che)",
    # Dữ liệu cá nhân
    "pii:full:read": "Xem số điện thoại và CCCD đầy đủ (bắt buộc nhập lý do, bị ghi log)",
    # Vận hành chuyến
    "ops:fleet:read": "Xem bản đồ đội xe thời gian thực",
    "trip:trip:read_all": "Xem mọi chuyến",
    "trip:trip:assign": "Gán tài xế thủ công cho chuyến",
    "trip:trip:cancel": "Huỷ chuyến thay người dùng",
    # Vận hành tài xế
    "driver:profile:read": "Xem hồ sơ tài xế",
    "driver:profile:approve": "Duyệt / từ chối hồ sơ và eKYC",
    "driver:account:lock": "Khoá hoặc mở khoá tài khoản tài xế",
    # Rủi ro & gian lận
    "risk:queue:read": "Xem hàng đợi review gian lận và bằng chứng",
    "risk:penalty:propose": "Đề xuất phạt hoặc khoá (vai trò maker)",
    "risk:penalty:approve": "Duyệt đề xuất phạt hoặc khoá (vai trò checker)",
    # Tài chính
    "finance:reconciliation:read": "Xem báo cáo đối soát",
    "finance:wallet:read": "Xem ví và ký quỹ của tài xế",
    "finance:payout:create": "Tạo lệnh chi (maker)",
    "finance:payout:approve": "Duyệt lệnh chi (checker)",
    "finance:escrow_refund:approve": "Duyệt hoàn ký quỹ",
    # Giá & khuyến mãi
    "pricing:rule:write": "Sửa bảng giá, khung giờ, khung cao điểm",
    "pricing:promo:write": "Quản lý khuyến mãi và vùng trợ cấp",
    # Đối tác
    "partner:partner:read": "Xem hồ sơ đối tác",
    "partner:partner:write": "Tạo, sửa hồ sơ đối tác và hoa hồng",
    "partner:commission:read": "Xem hoa hồng và kỳ chi trả đối tác",
    # Chăm sóc khách hàng
    "support:conversation:read_own": "Xem hội thoại được phân công",
    "support:conversation:read_all": "Xem mọi hội thoại",
    "support:ticket:write": "Tạo và xử lý ticket",
    "support:refund:approve": "Duyệt hoàn tiền trong hạn mức",
    # Báo cáo
    "analytics:report:read": "Xem báo cáo KPI và unit economics",
}

# Bộ quyền chỉ-đọc, dùng cho vai trò auditor.
READ_ONLY_PERMISSIONS = tuple(
    code
    for code in PERMISSIONS
    if code.endswith((":read", ":read_all")) and code != "pii:full:read"
)

# --- 12 vai trò -----------------------------------------------------------------------
# Cột "Không được" trong tài liệu phân định quan trọng ngang cột "Quyền tiêu biểu": ví dụ
# `finance_accountant` TẠO lệnh chi nhưng không được duyệt, `finance_manager` thì ngược lại.
# Đó chính là maker-checker, và nó chỉ có tác dụng khi không ai giữ cả hai quyền.
ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "super_admin": ("Quản trị hệ thống", (WILDCARD,)),
    "ops_manager": (
        "Trưởng vận hành",
        (
            "ops:fleet:read",
            "trip:trip:read_all",
            "trip:trip:assign",
            "trip:trip:cancel",
            "user:profile:read",
            "pii:full:read",
            "driver:profile:read",
            "driver:account:lock",
            "risk:queue:read",
            "risk:penalty:approve",
            "support:conversation:read_all",
            "analytics:report:read",
            "audit:log:read",
        ),
    ),
    "dispatcher": (
        "Điều phối",
        (
            "ops:fleet:read",
            "user:profile:read",
            "trip:trip:read_all",
            "trip:trip:assign",
            "trip:trip:cancel",
        ),
    ),
    "cs_agent": (
        "Nhân viên CSKH",
        (
            "support:conversation:read_own",
            "support:ticket:write",
            "trip:trip:read_all",
            "user:profile:read",
        ),
    ),
    "cs_lead": (
        "Trưởng nhóm CSKH",
        (
            "support:conversation:read_all",
            "support:ticket:write",
            "support:refund:approve",
            "trip:trip:read_all",
            "user:profile:read",
            "pii:full:read",
            "driver:profile:read",
        ),
    ),
    "driver_ops": (
        "Vận hành tài xế",
        (
            "driver:profile:read",
            "driver:profile:approve",
            "driver:account:lock",
            "trip:trip:read_all",
            "user:profile:read",
            "pii:full:read",
        ),
    ),
    "risk_analyst": (
        "Chuyên viên kiểm soát rủi ro",
        (
            "risk:queue:read",
            "risk:penalty:propose",
            "trip:trip:read_all",
            "driver:profile:read",
            "user:profile:read",
            "pii:full:read",
            "finance:wallet:read",
        ),
    ),
    "finance_accountant": (
        "Kế toán",
        (
            "finance:reconciliation:read",
            "finance:wallet:read",
            "finance:payout:create",
            "analytics:report:read",
        ),
    ),
    "finance_manager": (
        "Trưởng phòng tài chính",
        (
            "finance:reconciliation:read",
            "finance:wallet:read",
            "finance:payout:approve",
            "finance:escrow_refund:approve",
            "analytics:report:read",
        ),
    ),
    "partner_manager": (
        "Quản lý đối tác",
        ("partner:partner:read", "partner:partner:write", "partner:commission:read"),
    ),
    "marketing": ("Marketing", ("pricing:rule:write", "pricing:promo:write")),
    "auditor": ("Kiểm toán nội bộ", READ_ONLY_PERMISSIONS),
}
