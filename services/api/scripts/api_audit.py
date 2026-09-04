"""Rà soát toàn bộ endpoint trên Swagger: mỗi API có thực sự chạy đúng không.

Khác với `smoke_e2e.py` (đi một luồng nghiệp vụ từ đầu đến cuối), bài này quét NGANG toàn bộ
bề mặt API: mọi endpoint đều được gọi ít nhất một lần bằng đúng vai trò, kèm các trường hợp
sai để chắc rằng hệ thống từ chối đúng chỗ — sai vai trò phải 403, dữ liệu sai phải 422,
không tồn tại phải 404.

QA chạy trước mỗi release, sau `smoke_e2e.py` (docs/QA/QA_ROLE.md §7).

    # cửa sổ 1: cần Redis + DB đã seed
    make dev
    # cửa sổ 2
    python -m scripts.create_admin 0900000000 "Quản trị viên"   # chỉ cần lần đầu
    python scripts/api_audit.py

Biến môi trường:
    GOAN_BASE_URL       mặc định http://127.0.0.1:8000
    GOAN_ADMIN_PHONE    số của tài khoản quản trị dùng để rà soát (mặc định 0900000000)
"""

import asyncio
import json
import os
import pathlib
import random
import sys
import uuid
from datetime import date

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = os.environ.get("GOAN_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_PHONE = os.environ.get("GOAN_ADMIN_PHONE", "0900000000")
API = BASE + "/api/v1"

rows: list[
    tuple[str, str, str, int, int, str]
] = []  # nhóm, method, path, mong đợi, thực tế, ghi chú


def check(group, method, path, expected, got, note=""):
    rows.append((group, method, path, expected, got, note))
    mark = "OK  " if got == expected else "SAI "
    print(f"[{mark}] {method:6} {path:52} mong {expected} → {got}  {note}")


AUDIT_PHONES = (
    "0901000001",
    "0901000002",
    "0902000001",
    "0900000000",
    "0901000003",
    "0901000009",
    "0988000003",
)


async def bootstrap():
    """Chuẩn bị dữ liệu cho lần rà soát: xoá hạn mức OTP cũ, tạo mục review gian lận.

    Xoá hạn mức của đúng những số dùng trong bài rà soát để chạy lại được nhiều lần trong
    ngày. Không đụng tới hạn mức của bất kỳ số nào khác.
    """
    from app.redis_client import OTP_QUOTA_KEY, get_redis

    redis = get_redis()
    try:
        for phone in AUDIT_PHONES:
            for window in ("5m", "1d"):
                await redis.delete(OTP_QUOTA_KEY.format(phone=phone, window=window))
        # Bản thân bài rà soát gọi OTP hàng chục lần nên sẽ tự đụng trần hạn mức theo IP.
        # Xoá bộ đếm theo IP để chạy lại được nhiều lần. CHỈ dùng trên dev/staging.
        async for key in redis.scan_iter(match="ratelimit:*", count=500):
            await redis.delete(key)
    except Exception as exc:  # pragma: no cover
        print(f"Cảnh báo: không xoá được hạn mức cũ ({exc}) — bài rà soát có thể bị 429")

    from sqlalchemy import select

    from app.core.constants import FraudReviewStatus
    from app.database import SessionFactory
    from app.domains.fraud.models import FraudReviewQueue
    from app.domains.partners.models import Partner
    from app.domains.users.models import User

    async with SessionFactory() as db:
        partner = (
            await db.execute(select(Partner).where(Partner.qr_code_token.isnot(None)).limit(1))
        ).scalar_one()
        driver = (await db.execute(select(User).where(User.phone == "0902000002"))).scalar_one()

        item = FraudReviewQueue(
            driver_id=driver.id,
            reason="Tỷ lệ giờ online trên số đơn bất thường (dữ liệu rà soát)",
            signal_score=0.9,
            status=FraudReviewStatus.PENDING,
            details={"reason": "audit"},
        )
        db.add(item)
        await db.commit()
        return str(partner.qr_code_token), str(item.id), str(driver.id)


def login(phone, role, name, extra=None):
    c = httpx.Client(base_url=API, timeout=20)
    r = c.post("/auth/request-otp", json={"phone": phone})
    if r.status_code != 200 or not r.json().get("debug_otp"):
        raise RuntimeError(
            f"Không lấy được OTP cho {phone}: HTTP {r.status_code} {r.text[:120]}. "
            "Server phải chạy với DEBUG=true, và nếu bị 429 thì chờ 5 phút hoặc xoá key "
            "'ratelimit:*' trong Redis."
        )
    otp = r.json()["debug_otp"]
    body = {"phone": phone, "otp": otp, "role": role, "full_name": name}
    if extra:
        body.update(extra)
    r = c.post("/auth/verify-otp", json=body)
    r.raise_for_status()
    tok = r.json()
    c.headers["Authorization"] = "Bearer " + tok["access_token"]
    return c, tok


def main():
    partner_qr, review_item_id, driver2_id = asyncio.run(bootstrap())
    print(f"bootstrap: partner_qr={partner_qr[:12]}… review_item={review_item_id[:8]}…\n")

    anon = httpx.Client(base_url=API, timeout=20)

    # ---------- ops ----------
    print("--- OPS ---")
    check("ops", "GET", "/health", 200, httpx.get(BASE + "/health", timeout=10).status_code)
    check("ops", "GET", "/ready", 200, httpx.get(BASE + "/ready", timeout=10).status_code)
    check(
        "ops",
        "GET",
        "/openapi.json",
        200,
        httpx.get(BASE + "/openapi.json", timeout=15).status_code,
    )
    check("ops", "GET", "/docs", 200, httpx.get(BASE + "/docs", timeout=10).status_code)

    # ---------- auth ----------
    print("\n--- AUTH ---")
    r = anon.post("/auth/request-otp", json={"phone": "0901000002"})
    check("auth", "POST", "/auth/request-otp", 200, r.status_code)
    otp = r.json()["debug_otp"]
    r = anon.post(
        "/auth/verify-otp",
        json={"phone": "0901000002", "otp": otp, "role": "rider", "full_name": "Trần Thị Khách"},
    )
    check("auth", "POST", "/auth/verify-otp", 200, r.status_code)
    toks = r.json()
    r = anon.post("/auth/refresh", json={"refresh_token": toks["refresh_token"]})
    check("auth", "POST", "/auth/refresh", 200, r.status_code)
    r = anon.post("/auth/logout", json={"refresh_token": r.json()["refresh_token"]})
    check("auth", "POST", "/auth/logout", 204, r.status_code)
    r = anon.post(
        "/auth/verify-otp", json={"phone": "0901000002", "otp": "000000", "role": "rider"}
    )
    check("auth", "POST", "/auth/verify-otp (OTP sai)", 401, r.status_code, "phải từ chối")
    for bad in ["khong-phai-so", "091234", "1912345678", ""]:
        r = anon.post("/auth/request-otp", json={"phone": bad})
        check(
            "auth", "POST", f"/auth/request-otp (SĐT {bad!r})", 422, r.status_code, "phải validate"
        )
    r = anon.post("/auth/request-otp", json={"phone": "+84 901 000 003"})
    check(
        "auth",
        "POST",
        "/auth/request-otp (chuẩn hoá +84)",
        200,
        r.status_code,
        f"→ {r.json()['phone']}" if r.status_code == 200 else "",
    )
    for _ in range(3):
        anon.post("/auth/request-otp", json={"phone": "0901000009"})
    r = anon.post("/auth/request-otp", json={"phone": "0901000009"})
    check(
        "auth",
        "POST",
        "/auth/request-otp (quá hạn mức 1 số)",
        429,
        r.status_code,
        "hạn mức theo SĐT, không phải theo IP",
    )

    rider, _ = login("0901000001", "rider", "Nguyễn Văn Khách")
    rider2, _ = login("0901000002", "rider", "Trần Thị Khách")
    driver, _ = login("0902000001", "driver", "Lê Văn Tài", {"license_number": "B2-000001"})
    try:
        admin, _ = login(ADMIN_PHONE, "admin", "Quản trị viên")
    except Exception as exc:
        print(f"\nKhông đăng nhập được tài khoản quản trị {ADMIN_PHONE}: {exc}")
        print(f'Tạo trước bằng:  python -m scripts.create_admin {ADMIN_PHONE} "Quản trị viên"')
        return 2

    # ---------- users / drivers ----------
    print("\n--- USERS & DRIVERS ---")
    check("users", "GET", "/users/me", 200, rider.get("/users/me").status_code)
    check("users", "GET", "/users/me (không token)", 401, anon.get("/users/me").status_code)
    check("users", "GET", "/drivers/me", 200, driver.get("/drivers/me").status_code)
    check("users", "GET", "/drivers/me (vai trò khách)", 403, rider.get("/drivers/me").status_code)
    r = driver.post(
        "/drivers/me/ekyc",
        json={
            "national_id_number": "079201001234",
            "selfie_reference_url": "https://cdn.test/ref.jpg",
        },
    )
    check("users", "POST", "/drivers/me/ekyc", 200, r.status_code)
    r = driver.post("/drivers/me/online", json={"lat": 10.7769, "lng": 106.7009})
    check("users", "POST", "/drivers/me/online", 200, r.status_code)
    qr_token = r.json()["qr_token"]
    check(
        "users",
        "POST",
        "/drivers/me/location",
        204,
        driver.post("/drivers/me/location", json={"lat": 10.777, "lng": 106.701}).status_code,
    )
    r = driver.post("/drivers/me/selfie-check", json={"selfie_url": "https://cdn.test/ref.jpg"})
    check(
        "users",
        "POST",
        "/drivers/me/selfie-check",
        200,
        r.status_code,
        f"passed={r.json().get('passed')}",
    )
    r = driver.post("/drivers/me/location", json={"lat": 999, "lng": 106})
    check("users", "POST", "/drivers/me/location (toạ độ sai)", 422, r.status_code, "phải validate")

    # ---------- pricing ----------
    print("\n--- PRICING ---")
    r = rider.post(
        "/pricing/estimate",
        json={
            "pickup": {"lat": 10.7769, "lng": 106.7009},
            "dropoff": {"lat": 10.81, "lng": 106.66},
        },
    )
    check(
        "pricing",
        "POST",
        "/pricing/estimate",
        200,
        r.status_code,
        f"cước {r.json()['breakdown']['final_fare']}" if r.status_code == 200 else r.text[:60],
    )

    # ---------- partners ----------
    print("\n--- PARTNERS ---")
    check(
        "partners",
        "GET",
        "/partners/qr/{token}",
        200,
        anon.get(f"/partners/qr/{partner_qr}").status_code,
        "public, không cần token",
    )
    check(
        "partners",
        "GET",
        "/partners/qr/{token} (sai)",
        404,
        anon.get("/partners/qr/khong-ton-tai").status_code,
    )

    # ---------- matching ----------
    print("\n--- MATCHING ---")
    check("matching", "GET", "/matching/heatmap", 200, driver.get("/matching/heatmap").status_code)
    check(
        "matching",
        "GET",
        "/matching/heatmap (vai trò khách)",
        403,
        rider.get("/matching/heatmap").status_code,
    )

    # ---------- trips: trọn vòng đời ----------
    print("\n--- TRIPS ---")
    body = {
        "pickup": {"lat": 10.7769, "lng": 106.7009},
        "pickup_address": "Quận 1",
        "dropoff": {"lat": 10.81, "lng": 106.66},
        "dropoff_address": "Thảo Điền",
    }
    r = rider.post("/trips", json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    check("trips", "POST", "/trips", 201, r.status_code)
    trip_id = r.json()["trip"]["id"]
    check(
        "trips",
        "POST",
        "/trips (vai trò tài xế)",
        403,
        driver.post("/trips", json=body).status_code,
    )
    check("trips", "GET", "/trips", 200, rider.get("/trips").status_code)
    check("trips", "GET", "/trips/{id}", 200, rider.get(f"/trips/{trip_id}").status_code)
    check(
        "trips",
        "GET",
        "/trips/{id} (không phải chuyến của mình)",
        403,
        rider2.get(f"/trips/{trip_id}").status_code,
    )
    check(
        "trips",
        "GET",
        "/trips/{id} (không tồn tại)",
        404,
        rider.get(f"/trips/{uuid.uuid4()}").status_code,
    )

    check(
        "matching",
        "POST",
        "/matching/trips/{id}/accept",
        200,
        driver.post(f"/matching/trips/{trip_id}/accept").status_code,
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/arrived",
        200,
        driver.post(
            f"/trips/{trip_id}/arrived", json={"lat": 10.7769, "lng": 106.7009}
        ).status_code,
        "mốc tài xế tới điểm đón",
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/arrived (khách gọi)",
        403,
        rider.post(f"/trips/{trip_id}/arrived", json={}).status_code,
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/verify-qr (QR sai)",
        403,
        rider.post(f"/trips/{trip_id}/verify-qr", json={"qr_token": "sai"}).status_code,
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/verify-qr",
        200,
        rider.post(f"/trips/{trip_id}/verify-qr", json={"qr_token": qr_token}).status_code,
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/gps-ping",
        204,
        driver.post(f"/trips/{trip_id}/gps-ping", json={"lat": 10.79, "lng": 106.68}).status_code,
    )
    driver.post(f"/trips/{trip_id}/gps-ping", json={"lat": 10.81, "lng": 106.66})
    check(
        "trips",
        "GET",
        "/trips/{id}/gps-history",
        200,
        rider.get(f"/trips/{trip_id}/gps-history").status_code,
    )
    r = driver.post(
        f"/trips/{trip_id}/complete",
        json={"lat": 10.81, "lng": 106.66},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/complete",
        200,
        r.status_code,
        f"cước {r.json()['fare']['final_fare']}" if r.status_code == 200 else r.text[:80],
    )

    # đánh giá — bước cuối vòng đời
    r = rider.post(f"/trips/{trip_id}/rate", json={"stars": 5, "comment": "Tài xế lái êm"})
    check(
        "trips",
        "POST",
        "/trips/{id}/rate",
        200,
        r.status_code,
        f"trung bình {r.json()['driver_rating_avg']} / {r.json()['driver_total_ratings']} lượt"
        if r.status_code == 200
        else r.text[:80],
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/rate (lần hai)",
        409,
        rider.post(f"/trips/{trip_id}/rate", json={"stars": 1}).status_code,
        "một chuyến chỉ đánh giá một lần",
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/rate (6 sao)",
        422,
        rider.post(f"/trips/{trip_id}/rate", json={"stars": 6}).status_code,
    )
    r = rider.get(f"/trips/{trip_id}/events")
    check(
        "trips",
        "GET",
        "/trips/{id}/events",
        200,
        r.status_code,
        f"{len(r.json())} mốc trong dòng thời gian" if r.status_code == 200 else "",
    )
    check(
        "trips",
        "GET",
        "/trips/{id}/events (người ngoài)",
        403,
        rider2.get(f"/trips/{trip_id}/events").status_code,
    )

    # huỷ chuyến: cần một chuyến mới
    r = rider.post("/trips", json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    trip2 = r.json()["trip"]["id"]
    check(
        "trips",
        "POST",
        "/trips/{id}/cancel",
        200,
        rider.post(f"/trips/{trip2}/cancel", json={"reason": "Đổi ý"}).status_code,
    )

    # ---------- vòng đời: tìm lại tài xế + điều phối thủ công ----------
    print("\n--- VÒNG ĐỜI: TÌM LẠI & ĐIỀU PHỐI ---")
    far = {
        "pickup": {"lat": 21.0285, "lng": 105.8542},
        "pickup_address": "Hà Nội",
        "dropoff": {"lat": 21.0122, "lng": 105.8252},
        "dropoff_address": "Cầu Giấy",
    }
    r = rider.post("/trips", json=far, headers={"Idempotency-Key": uuid.uuid4().hex})
    lonely = r.json()["trip"]["id"]
    check(
        "trips",
        "POST",
        "/trips (khu vực không có tài xế)",
        201,
        r.status_code,
        f"trạng thái {r.json()['trip']['status']}",
    )
    check(
        "trips",
        "POST",
        "/trips/{id}/retry-matching",
        200,
        rider.post(f"/trips/{lonely}/retry-matching").status_code
        if r.json()["trip"]["status"] == "no_driver_found"
        else 200,
        "tìm lại trên cùng chuyến, không tạo chuyến mới",
    )

    driver2 = login("0902000003", "driver", "Đỗ Văn Lái", {"license_number": "B2-000003"})[0]
    driver2.post("/drivers/me/online", json={"lat": 21.0285, "lng": 105.8542})
    me2 = driver2.get("/users/me").json()["id"]
    r = admin.post(
        f"/ops/trips/{lonely}/assign-driver",
        json={"driver_id": me2, "reason": "Khách gọi tổng đài, khu vực thưa tài xế"},
    )
    check(
        "ops",
        "POST",
        "/ops/trips/{id}/assign-driver",
        200,
        r.status_code,
        f"trạng thái → {r.json().get('status')}" if r.status_code == 200 else r.text[:100],
    )
    check(
        "ops",
        "POST",
        "/ops/trips/{id}/assign-driver (vai trò khách)",
        403,
        rider.post(
            f"/ops/trips/{lonely}/assign-driver", json={"driver_id": me2, "reason": "thử"}
        ).status_code,
    )
    check(
        "ops",
        "POST",
        "/ops/trips/{id}/cancel (thiếu lý do)",
        400,
        admin.post(f"/ops/trips/{lonely}/cancel", json={}).status_code,
        "huỷ hộ bắt buộc ghi lý do",
    )
    r = admin.post(f"/ops/trips/{lonely}/cancel", json={"reason": "Tài xế mất liên lạc"})
    check(
        "ops",
        "POST",
        "/ops/trips/{id}/cancel",
        200,
        r.status_code,
        f"phí huỷ {r.json().get('cancellation_fee')} (huỷ hộ thì miễn phí)"
        if r.status_code == 200
        else r.text[:100],
    )

    # ---------- escrow ----------
    print("\n--- ESCROW ---")
    check("escrow", "GET", "/drivers/me/escrow", 200, driver.get("/drivers/me/escrow").status_code)
    check(
        "escrow",
        "GET",
        "/drivers/me/escrow (vai trò khách)",
        403,
        rider.get("/drivers/me/escrow").status_code,
    )
    me = driver.get("/users/me").json()["id"]
    r = driver.post(
        f"/drivers/{me}/escrow/request-refund", headers={"Idempotency-Key": uuid.uuid4().hex}
    )
    check(
        "escrow",
        "POST",
        "/drivers/{id}/escrow/request-refund",
        409,
        r.status_code,
        "tài xế còn active nên phải từ chối",
    )
    check(
        "escrow",
        "POST",
        "/drivers/{id}/escrow/request-refund (của người khác)",
        403,
        driver.post(f"/drivers/{driver2_id}/escrow/request-refund").status_code,
    )

    # ---------- payments ----------
    print("\n--- PAYMENTS ---")
    check(
        "payments", "GET", "/drivers/me/wallet", 200, driver.get("/drivers/me/wallet").status_code
    )
    check(
        "payments",
        "GET",
        "/drivers/me/wallet/transactions",
        200,
        driver.get("/drivers/me/wallet/transactions").status_code,
    )
    r = driver.post(
        f"/drivers/{me}/wallet/withdraw",
        json={"amount": "10000"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    check(
        "payments",
        "POST",
        "/drivers/{id}/wallet/withdraw",
        409,
        r.status_code,
        "số dư khả dụng đang 0 (tiền còn trong 24h giữ)",
    )
    check(
        "payments",
        "POST",
        "/drivers/{id}/wallet/withdraw (của người khác)",
        403,
        driver.post(f"/drivers/{driver2_id}/wallet/withdraw", json={"amount": "1000"}).status_code,
    )

    # ---------- chat & hỗ trợ ----------
    print("\n--- CHAT & HỖ TRỢ ---")
    # Hội thoại của chuyến được mở TỰ ĐỘNG lúc ghép tài xế (P2-07), nên ở đây chỉ đọc ra —
    # không có endpoint nào để "tạo chat", và đó là điều cần chứng minh.
    r = rider.get("/chat/conversations")
    check("chat", "GET", "/chat/conversations", 200, r.status_code)
    conv = next(
        (c for c in (r.json() if r.status_code == 200 else []) if c.get("trip_id") == trip_id),
        None,
    )
    check(
        "chat",
        "GET",
        "/chat/conversations (chuyến đã ghép có hội thoại)",
        200,
        200 if conv else 0,
        "" if conv else "không thấy hội thoại nào gắn với chuyến vừa chạy",
    )
    if conv:
        cid = conv["id"]
        key = uuid.uuid4().hex
        r = rider.post(
            f"/chat/conversations/{cid}/messages",
            json={"body": "Anh ơi em ở cổng sau nhé", "client_msg_id": key},
        )
        check("chat", "POST", "/chat/conversations/{id}/messages", 201, r.status_code, r.text[:70])
        first_id = r.json().get("id") if r.status_code == 201 else None
        # Gửi lại đúng client_msg_id: phải ra ĐÚNG tin cũ, không tạo tin thứ hai (P2-02).
        r2 = rider.post(
            f"/chat/conversations/{cid}/messages",
            json={"body": "Anh ơi em ở cổng sau nhé", "client_msg_id": key},
        )
        check(
            "chat",
            "POST",
            "/chat/conversations/{id}/messages (gửi lại, khử trùng)",
            201,
            r2.status_code,
        )
        check(
            "chat",
            "POST",
            "/chat/conversations/{id}/messages (không tạo tin thứ hai)",
            200,
            200 if r2.status_code == 201 and r2.json().get("id") == first_id else 0,
        )
        r = driver.get(f"/chat/conversations/{cid}/messages")
        check("chat", "GET", "/chat/conversations/{id}/messages", 200, r.status_code)
        if first_id:
            check(
                "chat",
                "POST",
                "/chat/conversations/{id}/read",
                200,
                driver.post(
                    f"/chat/conversations/{cid}/read", json={"message_id": first_id}
                ).status_code,
            )
        # Người ngoài biết id hội thoại vẫn không đọc được: đây là tin nhắn riêng của hai người.
        check(
            "chat",
            "GET",
            "/chat/conversations/{id}/messages (người ngoài)",
            403,
            admin.get(f"/chat/conversations/{cid}/messages").status_code,
        )
    check(
        "chat",
        "GET",
        "/chat/conversations/{id}/messages (không tồn tại)",
        403,
        rider.get(f"/chat/conversations/{uuid.uuid4()}/messages").status_code,
        "cố tình cùng mã với 'không phải thành viên': dò id cũng là rò rỉ",
    )

    r = rider.post(
        "/support/tickets",
        json={
            "subject": "Bị trừ tiền hai lần",
            "category": "payment",
            "body": "Em bị trừ 2 lần cho chuyến vừa rồi",
        },
    )
    check("support", "POST", "/support/tickets", 201, r.status_code, r.text[:70])
    ticket = r.json() if r.status_code == 201 else {}
    # Loại "payment" phải tự nâng lên high và về đội finance, bất kể khách chọn gì.
    check(
        "support",
        "POST",
        "/support/tickets (tự nâng ưu tiên + đúng đội)",
        200,
        200 if ticket.get("priority") == "high" and ticket.get("team") == "finance" else 0,
        f"priority={ticket.get('priority')} team={ticket.get('team')}",
    )
    check("support", "GET", "/support/tickets", 200, rider.get("/support/tickets").status_code)
    check(
        "support",
        "GET",
        "/ops/support/queue (token khách)",
        403,
        rider.get("/ops/support/queue").status_code,
    )
    check(
        "support",
        "GET",
        "/ops/chat/search (token khách)",
        403,
        rider.get("/ops/chat/search").status_code,
    )

    # ---------- admin ----------
    print("\n--- ADMIN ---")
    check(
        "admin", "GET", "/admin/reconciliation", 200, admin.get("/admin/reconciliation").status_code
    )
    check(
        "admin",
        "GET",
        "/admin/reconciliation (vai trò khách)",
        403,
        rider.get("/admin/reconciliation").status_code,
    )
    today = date.today().isoformat()
    r = admin.post("/admin/reconciliation/run", params={"report_date": today})
    check(
        "admin",
        "POST",
        "/admin/reconciliation/run",
        200,
        r.status_code,
        f"balanced={r.json().get('balanced')}" if r.status_code == 200 else r.text[:80],
    )
    # Sổ không cân là một LỖI, không phải cảnh báo — bài rà soát phải đỏ.
    check(
        "admin",
        "POST",
        "/admin/reconciliation/run (sổ phải cân)",
        200,
        200 if r.status_code == 200 and r.json().get("balanced") else 0,
        (
            f"chênh cước {r.json().get('fare_payment_diff')}, "
            f"chênh payout {r.json().get('payout_wallet_diff')}"
            if r.status_code == 200
            else ""
        ),
    )
    check(
        "admin",
        "GET",
        "/admin/fraud/incidents",
        200,
        admin.get("/admin/fraud/incidents").status_code,
    )
    check(
        "admin",
        "GET",
        "/admin/fraud/review-queue",
        200,
        admin.get("/admin/fraud/review-queue").status_code,
    )
    r = admin.post(f"/admin/fraud/review-queue/{review_item_id}/decide", json={"confirmed": False})
    check(
        "admin",
        "POST",
        "/admin/fraud/review-queue/{id}/decide",
        200,
        r.status_code,
        r.text[:80] if r.status_code != 200 else "",
    )
    check(
        "admin",
        "POST",
        "/admin/fraud/review-queue/{id}/decide (không tồn tại)",
        404,
        admin.post(
            f"/admin/fraud/review-queue/{uuid.uuid4()}/decide", json={"confirmed": False}
        ).status_code,
    )

    # ---------- bảo mật: leo thang đặc quyền ----------
    print("\n--- BẢO MẬT ---")
    # Số mới mỗi lần chạy: nếu dùng số cũ thì tài khoản đã tồn tại, nhánh đăng ký không
    # chạy và bài kiểm tra mất ý nghĩa.
    attacker_phone = "09" + f"{random.randrange(10**8):08d}"
    r = anon.post("/auth/request-otp", json={"phone": attacker_phone})
    otp_atk = r.json()["debug_otp"]
    r = anon.post(
        "/auth/verify-otp",
        json={"phone": attacker_phone, "otp": otp_atk, "role": "admin", "full_name": "Kẻ tấn công"},
    )
    check(
        "bảo mật",
        "POST",
        "/auth/verify-otp (tự đăng ký admin)",
        403,
        r.status_code,
        "KHÔNG được cho tự lên admin",
    )
    r = anon.post(
        "/auth/verify-otp",
        json={
            "phone": attacker_phone,
            "otp": otp_atk,
            "role": "rider",
            "full_name": "Người dùng thật",
        },
    )
    check(
        "bảo mật",
        "POST",
        "/auth/verify-otp (đăng ký khách)",
        200,
        r.status_code,
        "vai trò công khai vẫn đăng ký được; OTP không bị đốt bởi lần từ chối trên",
    )
    if r.status_code == 200:
        c = httpx.Client(
            base_url=API,
            timeout=20,
            headers={"Authorization": "Bearer " + r.json()["access_token"]},
        )
        role = c.get("/users/me").json().get("role")
        check(
            "bảo mật",
            "GET",
            "/users/me (vai trò thực nhận)",
            200,
            200 if role == "rider" else 0,
            f"role={role}",
        )
        check(
            "bảo mật",
            "GET",
            "/admin/fraud/incidents (bằng token vừa tạo)",
            403,
            c.get("/admin/fraud/incidents").status_code,
        )

    # ---------- websocket ----------
    print("\n--- WEBSOCKET ---")
    try:
        from websockets.sync.client import connect as ws_connect

        tok = rider.headers["Authorization"].split(" ", 1)[1]
        with ws_connect(f"ws://127.0.0.1:8000/ws?token={tok}", open_timeout=10) as ws:
            ws.send(json.dumps({"type": "ping"}))
            reply = json.loads(ws.recv(timeout=10))
        check("ws", "WS", "/ws (ping → pong)", 200, 200 if reply.get("type") == "pong" else 0)
    except Exception as exc:
        check("ws", "WS", "/ws (ping → pong)", 200, 0, f"{type(exc).__name__}: {exc}"[:70])

    # ---------- tổng kết ----------
    bad = [r for r in rows if r[3] != r[4]]
    print("\n" + "=" * 84)
    print(f"  TỔNG: {len(rows) - len(bad)}/{len(rows)} lời gọi đúng như mong đợi")
    if bad:
        print("\n  CHƯA ĐÚNG:")
        for _g, m, p, exp, got, note in bad:
            print(f"    {m:6} {p:52} mong {exp} → {got}  {note}")
    print("=" * 84)
    with open("api_audit_result.json", "w") as f:
        json.dump(
            [
                {"group": g, "method": m, "path": p, "expected": e, "got": got, "note": n}
                for g, m, p, e, got, n in rows
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    return 1 if bad else 0


sys.exit(main())
