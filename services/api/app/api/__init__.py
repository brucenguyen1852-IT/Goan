"""Bề mặt API tách theo đối tượng sử dụng (tài liệu phân định §3.1) — P1-08.

Năm nhóm: `rider`, `driver`, `ops`, `partner`, `public`. Cùng một nghiệp vụ có thể xuất hiện ở
hai nhóm (CSKH kết thúc chuyến hộ tài xế mất mạng), nhưng khi đó khác lớp quyền và khác dấu
vết, không khác logic — nên nhóm là chuyện của ROUTER, không phải của service.

Cách làm ở đây có chủ đích: **không viết lại handler**. Mỗi route đã có được gắn thêm vào
router của nhóm tương ứng, nên `/api/v1/rider/trips` và `/api/v1/trips` chạy đúng cùng một
hàm, cùng một kiểm quyền. Đường dẫn cũ vẫn sống và bị đánh dấu `deprecated` trong OpenAPI để
client cũ có thời gian chuyển.

Bảng `AUDIENCES` bên dưới là câu trả lời kiểm chứng được cho câu hỏi "endpoint này của ai?".
Có test chốt: mọi route nghiệp vụ phải thuộc đúng một nhóm — quên khai báo là đỏ, chứ không
phải âm thầm rơi ra ngoài.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

# Tên hàm handler -> nhóm đối tượng. Một handler có thể phục vụ nhiều nhóm.
AUDIENCES: dict[str, tuple[str, ...]] = {
    # --- Không cần đăng nhập ---
    "request_otp": ("public",),
    "verify_otp": ("public",),
    "refresh": ("public",),
    "logout": ("public",),
    "partner_by_qr": ("public",),
    # --- Khách ---
    "me": ("rider", "driver"),
    "estimate_fare": ("rider",),
    "create_trip": ("rider",),
    "list_my_trips": ("rider",),
    "get_trip": ("rider", "driver"),
    "cancel_trip": ("rider",),
    "verify_qr": ("rider",),
    "gps_history": ("rider",),
    "rate_trip": ("rider",),
    "retry_matching": ("rider",),
    "trip_timeline": ("rider",),
    # --- Tài xế ---
    "my_driver_profile": ("driver",),
    "submit_ekyc": ("driver",),
    "go_online": ("driver",),
    "go_offline": ("driver",),
    "update_location": ("driver",),
    "selfie_check": ("driver",),
    "complete_trip": ("driver",),
    "gps_ping": ("driver",),
    "driver_arrived": ("driver",),
    "accept_trip": ("driver",),
    "satellite_heatmap": ("driver",),
    "my_escrow": ("driver",),
    "request_refund": ("driver",),
    "my_wallet": ("driver",),
    "my_wallet_transactions": ("driver",),
    "withdraw": ("driver",),
    # --- Chat & hỗ trợ: cùng một bề mặt cho cả hai bên của chuyến ---
    "list_conversations": ("rider", "driver"),
    "list_messages": ("rider", "driver"),
    "send_message": ("rider", "driver"),
    "mark_read": ("rider", "driver"),
    "create_ticket": ("rider", "driver"),
    "my_tickets": ("rider", "driver"),
    # --- Console (đã có sẵn bề mặt /ops riêng, liệt kê ở đây cho đủ bức tranh) ---
    "list_reconciliation_reports": ("ops",),
    "run_reconciliation": ("ops",),
    "list_incidents": ("ops",),
    "list_review_queue": ("ops",),
    "decide_review_item": ("ops",),
}

AUDIENCE_NAMES = ("rider", "driver", "ops", "partner", "public")

# `partner` hiện chưa có endpoint nào: Partner Portal là P6 và đối tác còn chưa có cách đăng
# nhập riêng. Nhóm vẫn được dựng sẵn để chỗ dành cho nó là thứ có thật trong mã, không phải
# lời hứa trong tài liệu.

# Tiền tố cũ cần cắt khi gắn vào router nhóm, để không thành /rider/trips/trips.
_STRIP_PREFIXES = ("/admin",)


def _clone_route(route: APIRoute, audience: str) -> dict:
    path = route.path
    for prefix in _STRIP_PREFIXES:
        if path.startswith(prefix):
            path = path[len(prefix) :] or "/"
    return {
        "path": path,
        "endpoint": route.endpoint,
        "methods": sorted(route.methods or []),
        "response_model": route.response_model,
        "status_code": route.status_code,
        "name": route.name,
        "summary": route.summary,
        "description": route.description,
        "tags": [f"{audience}"],
        "dependencies": list(route.dependencies),
        "response_class": route.response_class,
        "include_in_schema": route.include_in_schema,
    }


def build_audience_routers(source_routers: list[APIRouter]) -> dict[str, APIRouter]:
    """Dựng 5 router nhóm từ các router domain đang có.

    Trả về dict nhóm -> router (chỉ những nhóm thật sự có route).
    """
    # Dựng sẵn đủ 5 nhóm, kể cả nhóm chưa có endpoint nào, để bề mặt là thứ khai báo tường
    # minh chứ không phải hệ quả tình cờ của việc có hay chưa có route.
    built: dict[str, APIRouter] = {name: APIRouter(prefix=f"/{name}") for name in AUDIENCE_NAMES}
    for source in source_routers:
        for route in source.routes:
            if not isinstance(route, APIRoute):
                continue
            for audience in AUDIENCES.get(route.name, ()):
                built[audience].add_api_route(**_clone_route(route, audience))
    return built


def unassigned_routes(source_routers: list[APIRouter]) -> list[str]:
    """Route nghiệp vụ chưa được xếp vào nhóm nào. Dùng cho test — quên khai báo là đỏ."""
    missing = []
    for source in source_routers:
        for route in source.routes:
            if isinstance(route, APIRoute) and route.name not in AUDIENCES:
                missing.append(f"{route.name} ({route.path})")
    return sorted(missing)
