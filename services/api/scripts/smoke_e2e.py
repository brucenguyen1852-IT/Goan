"""Smoke test end-to-end — chạy trên một server GoAn đang chạy thật.

Khác với pytest: bài này gọi HTTP thật vào một tiến trình uvicorn thật, với Redis thật và
DB thật. Nó bắt được những thứ test in-process không thấy: thứ tự middleware, cấu hình sai,
Redis không kết nối được, migration chưa chạy.

QA chạy bài này trước mỗi lần release (docs/QA/QA_ROLE.md §7).

    # cửa sổ 1
    make dev
    # cửa sổ 2
    python scripts/smoke_e2e.py

Biến môi trường:
    GOAN_BASE_URL   mặc định http://127.0.0.1:8000
    GOAN_DB_PATH    đường dẫn file SQLite để kiểm tra audit log (mặc định ./goan_dev.db)
"""

import json
import os
import pathlib
import sqlite3
import sys
import uuid

import httpx

# Chạy được cả `python scripts/smoke_e2e.py` lẫn `python -m scripts.smoke_e2e`: cần thấy gói
# `app` để đọc DATABASE_URL, nếu không sẽ âm thầm quay về SQLite và ngã ở bước audit.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = os.environ.get("GOAN_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"
OK, BAD = "  OK ", " LỖI "
results = []


def show(step, ok, detail=""):
    results.append(ok)
    print(f"[{OK if ok else BAD}] {step}" + (f"  →  {detail}" if detail else ""))


def read_audit_rows():
    """(method, path, status_code, actor_role, payload, request_id, duration_ms) theo thứ tự thời gian.

    Chọn cách đọc theo DATABASE_URL: file SQLite ở dev, còn staging/production là Postgres.
    """
    columns = "method, path, status_code, actor_role, payload, request_id, duration_ms"
    order = "ORDER BY created_at"
    url = os.environ.get("GOAN_DATABASE_URL", "")
    if not url:
        try:
            from app.config import settings

            url = settings.DATABASE_URL
        except Exception:
            url = ""

    if url.startswith("postgres"):
        # Dùng engine async + asyncpg: đó là driver repo đã có sẵn. Thêm psycopg2 chỉ để chạy
        # một câu SELECT trong bài kiểm thử là bắt cả đội cài thêm một gói không dùng đến.
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        async def _fetch():
            engine = create_async_engine(url)
            async with engine.connect() as conn:
                result = await conn.execute(text(f"SELECT {columns} FROM audit_logs {order}"))
                data = [tuple(r) for r in result]
            await engine.dispose()
            return data

        rows = asyncio.run(_fetch())
        # payload là JSONB -> dict; phần sau của bài này so chuỗi nên đổi về chuỗi cho đồng nhất.
        return [
            (*r[:4], json.dumps(r[4], ensure_ascii=False) if r[4] is not None else None, *r[5:])
            for r in rows
        ]

    db_path = os.environ.get("GOAN_DB_PATH", "goan_dev.db")
    con = sqlite3.connect(db_path)
    try:
        return con.execute(f"SELECT {columns} FROM audit_logs {order}").fetchall()
    finally:
        con.close()


def login(phone, role, name, extra=None):
    c = httpx.Client(base_url=API, timeout=20)
    r = c.post("/auth/request-otp", json={"phone": phone})
    otp = r.json()["debug_otp"]
    body = {"phone": phone, "otp": otp, "role": role, "full_name": name}
    if extra:
        body.update(extra)
    r = c.post("/auth/verify-otp", json=body)
    r.raise_for_status()
    tok = r.json()
    c.headers["Authorization"] = "Bearer " + tok["access_token"]
    return c, tok


print("=" * 78)
print("  GoAn — chạy thử end-to-end trên server thật")
print("=" * 78)

# --- 1. Sức khoẻ hệ thống ---
print("\n1. SỨC KHOẺ HỆ THỐNG")
r = httpx.get(BASE + "/health", timeout=10)
show(
    "GET /health (liveness, không chạm DB)",
    r.status_code == 200 and "database" not in r.json(),
    json.dumps(r.json(), ensure_ascii=False),
)
show(
    "  có X-Request-ID để truy vết",
    bool(r.headers.get("X-Request-ID")),
    r.headers.get("X-Request-ID", "")[:16],
)
r = httpx.get(BASE + "/ready", timeout=10)
show(
    "GET /ready (readiness, kiểm DB + Redis)",
    r.status_code == 200 and r.json().get("ready"),
    json.dumps(r.json(), ensure_ascii=False),
)

# --- 2. Đăng nhập ---
print("\n2. ĐĂNG NHẬP OTP")
rider, rider_tok = login("0901000001", "rider", "Nguyễn Văn Khách")
show("Khách đăng nhập bằng SĐT + OTP", True, "0901000001")
driver, driver_tok = login("0902000001", "driver", "Lê Văn Tài", {"license_number": "B2-000001"})
show("Tài xế đăng nhập", True, "0902000001")

# --- 3. Báo giá ---
print("\n3. BÁO GIÁ TRƯỚC CHUYẾN")
r = rider.post(
    "/pricing/estimate",
    json={
        "pickup": {"lat": 10.7769, "lng": 106.7009},
        "dropoff": {"lat": 10.8100, "lng": 106.6600},
    },
)
est = r.json()
b = est["breakdown"]
show(
    "POST /pricing/estimate",
    r.status_code == 200,
    f"{est['time_band']} · {est['distance_km']}km · {est['duration_minutes']} phút",
)
print(f"        phí nền {b['base_fee']}  +  km {b['distance_fee']}  +  phút {b['time_fee']}")
print(
    f"        cước cuối {b['final_fare']}đ   |   tài xế nhận {b['driver_payout']}đ"
    f"   |   nền tảng {b['platform_commission']}đ"
)

# --- 4. Tài xế lên ca ---
print("\n4. TÀI XẾ LÊN CA")
r = driver.post("/drivers/me/online", json={"lat": 10.7769, "lng": 106.7009})
online = r.json()
qr_token = online.get("qr_token")
show(
    "POST /drivers/me/online (sinh QR động)",
    r.status_code == 200 and bool(qr_token),
    f"qr_token = {str(qr_token)[:18]}…",
)

# --- 5. Đặt chuyến + idempotency ---
print("\n5. ĐẶT CHUYẾN  &  KHỬ TRÙNG REQUEST")
idem = "demo-" + uuid.uuid4().hex[:8]
payload = {
    "pickup": {"lat": 10.7769, "lng": 106.7009},
    "pickup_address": "Quán nhậu Nguyễn Huệ",
    "dropoff": {"lat": 10.8100, "lng": 106.6600},
    "dropoff_address": "Chung cư Thảo Điền",
}
r1 = rider.post("/trips", json=payload, headers={"Idempotency-Key": idem})
trip = r1.json()["trip"]
show(
    "POST /trips lần 1",
    r1.status_code == 201,
    f"trip {trip['id'][:8]}… · trạng thái {trip['status']} · ước tính {trip['estimated_fare']}đ",
)
r2 = rider.post("/trips", json=payload, headers={"Idempotency-Key": idem})
show(
    "POST /trips lần 2 (cùng Idempotency-Key)",
    r2.headers.get("Idempotent-Replay") == "true" and r2.json()["trip"]["id"] == trip["id"],
    f"Idempotent-Replay: {r2.headers.get('Idempotent-Replay')} · cùng trip id → KHÔNG tạo chuyến thứ hai",
)

# --- 6. Ghép chuyến ---
print("\n6. GHÉP CHUYẾN")
r = driver.post(f"/matching/trips/{trip['id']}/accept")
show(
    "Tài xế nhận chuyến",
    r.status_code == 200,
    f"trạng thái → {r.json().get('status')}" if r.status_code == 200 else r.text[:120],
)

# --- 7. QR bắt buộc ---
print("\n7. QUÉT QR (chống đơn ma)")
r = rider.post(f"/trips/{trip['id']}/verify-qr", json={"qr_token": "qr-gia-mao"})
show("Quét QR SAI bị từ chối", r.status_code >= 400, f"HTTP {r.status_code}")
r = rider.post(f"/trips/{trip['id']}/verify-qr", json={"qr_token": qr_token})
show(
    "Quét QR đúng → chuyến vào in_progress",
    r.status_code == 200,
    f"trạng thái → {r.json().get('status')}" if r.status_code == 200 else r.text[:150],
)

# --- 8. GPS ---
print("\n8. GHI GPS DỌC ĐƯỜNG")
pts = [
    (10.7769, 106.7009),
    (10.7850, 106.6950),
    (10.7930, 106.6850),
    (10.8010, 106.6740),
    (10.8100, 106.6600),
]
okc = sum(
    1
    for la, ln in pts
    if driver.post(f"/trips/{trip['id']}/gps-ping", json={"lat": la, "lng": ln}).status_code == 204
)
show("Gửi 5 điểm GPS", okc == 5, f"{okc}/5 điểm được ghi")

# --- 9. Kết thúc chuyến ---
print("\n9. KẾT THÚC CHUYẾN — CHỐT TIỀN")
r = driver.post(
    f"/trips/{trip['id']}/complete",
    json={"lat": 10.8100, "lng": 106.6600},
    headers={"Idempotency-Key": "done-" + uuid.uuid4().hex[:8]},
)
if r.status_code == 200:
    d = r.json()
    f = d["fare"]
    show("POST /trips/{id}/complete", True, f"trạng thái → {d['trip']['status']}")
    print(
        f"        quãng đường thực tế {d['trip']['distance_km']}km · {d['trip']['duration_minutes']} phút"
    )
    print(f"        CƯỚC CUỐI          {f['final_fare']}đ")
    print(f"        tài xế được chia   {f['driver_payout']}đ")
    print(f"        trích ký quỹ 15%   {d['escrow_deducted']}đ")
    print(f"        tài xế THỰC NHẬN   {d['driver_actual_payout']}đ")
    print(
        f"        nền tảng giữ       {f['platform_commission']}đ  (đã gồm phí BH {f['insurance_fee']}đ + phí cổng {f['payment_gateway_fee']}đ)"
    )
    print(f"        phát hiện chạy vòng: {d['route_deviation_detected']}")
else:
    show("POST /trips/{id}/complete", False, f"HTTP {r.status_code} · {r.text[:200]}")

# --- 10. Ví & ký quỹ ---
print("\n10. VÍ  &  KÝ QUỸ TÀI XẾ")
w = driver.get("/drivers/me/wallet").json()
show(
    "GET /drivers/me/wallet",
    True,
    f"chờ về {w.get('pending_balance')}đ · khả dụng {w.get('available_balance')}đ",
)
e = driver.get("/drivers/me/escrow").json()
show(
    "GET /drivers/me/escrow",
    e.get("escrow_status") is not None,
    f"số dư {e.get('escrow_balance')}đ / định mức {e.get('escrow_target')}đ · {e.get('escrow_status')}",
)
for t in e.get("transactions", [])[:3]:
    print(
        f"        bút toán: {t['type']} {t['amount']}đ → số dư {t['balance_after']}đ · {t['note']}"
    )

# --- 11. Chat: hội thoại tự mở, khử trùng, đồng bộ bù (P2-21) ---
print("\n11. CHAT — MẤT SÓNG GIỮA CHỪNG RỒI GỬI LẠI")
r = rider.get("/chat/conversations")
conv = next((c for c in (r.json() if r.status_code == 200 else []) if c.get("trip_id")), None)
show(
    "Hội thoại chuyến TỰ mở lúc ghép tài xế",
    conv is not None,
    "không có endpoint nào để tạo chat — đó là điều cần chứng minh",
)
if conv:
    cid = conv["id"]
    r = rider.post(
        f"/chat/conversations/{cid}/messages",
        json={"body": "Anh ơi em ở cổng sau", "client_msg_id": "smoke-1"},
    )
    moc = r.json().get("created_at") if r.status_code == 201 else None
    show("Khách gửi được tin", r.status_code == 201, r.text[:100] if r.status_code != 201 else "")

    # Mất sóng: app không biết server đã nhận chưa nên bấm gửi lại ba lần.
    lai = [
        rider.post(
            f"/chat/conversations/{cid}/messages",
            json={"body": "Anh tới chưa ạ", "client_msg_id": "smoke-2"},
        )
        for _ in range(3)
    ]
    ids = {x.json().get("id") for x in lai if x.status_code == 201}
    show(
        "Bấm gửi lại 3 lần → vẫn đúng MỘT tin",
        len(ids) == 1,
        f"{len(ids)} tin được tạo cho cùng một client_msg_id",
    )

    driver.post(f"/chat/conversations/{cid}/messages", json={"body": "Anh đang tới"})
    r = rider.get(f"/chat/conversations/{cid}/messages", params={"after": moc})
    bu = [m["body"] for m in r.json()] if r.status_code == 200 else []
    show(
        "Có mạng lại → đồng bộ bù đủ tin đã lỡ",
        bu == ["Anh tới chưa ạ", "Anh đang tới"],
        f"nhận về: {bu}",
    )

    r = rider.post(
        "/chat/attachments",
        json={"conversation_id": cid, "content_type": "image/jpeg", "size_bytes": 200000},
    )
    show("Xin URL tải ảnh (ký hạn 15 phút)", r.status_code == 201, r.text[:100])
    if r.status_code == 201:
        att = r.json()["attachment_id"]
        r = rider.get(f"/chat/attachments/{att}")
        show(
            "URL đọc ảnh có hạn, không phải link cố định",
            r.status_code == 200 and "X-Expires=" in r.json().get("download_url", ""),
            r.text[:100] if r.status_code != 200 else "",
        )

    r = driver.post(
        f"/chat/conversations/{cid}/messages",
        json={"body": "Em chuyển khoản Vietcombank 0123456789 nhé, khỏi qua app"},
    )
    doc = rider.get(f"/chat/conversations/{cid}/messages")
    van_doc_duoc = r.status_code == 201 and any(
        "0123456789" in m["body"] for m in (doc.json() if doc.status_code == 200 else [])
    )
    show(
        "Rủ thanh toán ngoài app: GẮN CỜ nhưng KHÔNG chặn tin",
        van_doc_duoc,
        "chặn tin là đẩy hai bên sang Zalo và mất luôn dấu vết",
    )

# --- 12. Hỗ trợ: mở ticket, SLA, trả lời (P2-21) ---
print("\n12. HỖ TRỢ — MỞ TICKET VÀ CAM KẾT SLA")
r = rider.post(
    "/support/tickets",
    json={"subject": "Bị trừ tiền hai lần", "category": "payment", "priority": "low"},
)
t = r.json() if r.status_code == 201 else {}
show("Khách mở được ticket", r.status_code == 201, r.text[:100] if r.status_code != 201 else "")
show(
    "Khách chọn 'thấp' nhưng vấn đề TIỀN → tự nâng lên high, vào đội finance",
    t.get("priority") == "high" and t.get("team") == "finance",
    f"priority={t.get('priority')} team={t.get('team')}",
)
show(
    "Ticket có mã ngắn đọc được qua điện thoại",
    str(t.get("code", "")).startswith("GA-"),
    f"mã: {t.get('code')}",
)
show(
    "Hội thoại hỗ trợ đi kèm ticket, không phải gọi thêm API",
    bool(t.get("conversation_id")),
)

# --- 13. Xoay vòng refresh token ---
print("\n13. BẢO MẬT — XOAY VÒNG REFRESH TOKEN")
c = httpx.Client(base_url=API, timeout=20)
old_rt = rider_tok["refresh_token"]
r = c.post("/auth/refresh", json={"refresh_token": old_rt})
new_rt = r.json()["refresh_token"]
show("Refresh lần đầu → cấp token mới", r.status_code == 200 and new_rt != old_rt)
r = c.post("/auth/refresh", json={"refresh_token": old_rt})
show(
    "Dùng LẠI token cũ (mô phỏng token bị đánh cắp)",
    r.status_code == 401,
    f"HTTP {r.status_code} → thu hồi cả họ token",
)
r = c.post("/auth/refresh", json={"refresh_token": new_rt})
show(
    "Token hợp lệ của người dùng thật cũng bị vô hiệu",
    r.status_code == 401,
    f"HTTP {r.status_code} → buộc đăng nhập lại bằng OTP",
)

# --- 14. Rate limit ---
print("\n14. BẢO MẬT — CHẶN SPAM OTP (mỗi tin SMS là tiền thật)")
codes = [
    httpx.post(API + "/auth/request-otp", json={"phone": "0909999999"}, timeout=10).status_code
    for _ in range(7)
]
show("Gọi /auth/request-otp 7 lần liên tiếp", 429 in codes, f"mã trả về: {codes}")
print("        Hạn mức: 5 lượt / 5 phút. Kịch bản này đã dùng 2 lượt ở bước đăng nhập,")
print("        nên chỉ còn 3 lượt → đúng như quan sát. Hạn mức tính theo ĐỊA CHỈ IP.")

# --- 15. Audit log ---
print("\n15. AUDIT LOG — dấu vết thao tác")
# Đọc thẳng từ DB đang chạy, dù là SQLite (dev) hay Postgres (staging). Trước đây bài này
# chỉ mở được file SQLite, nên chạy trên staging là ngã ở đúng bước cuối.
rows = read_audit_rows()
show("Ghi được bản ghi audit", len(rows) > 0, f"{len(rows)} bản ghi cho các thao tác GHI")
otp_rows = [r for r in rows if "verify-otp" in r[1]]
masked = all('"otp": "***"' in (r[4] or "") for r in otp_rows) if otp_rows else False
show(
    "OTP bị che trong audit (Nghị định 13)",
    masked,
    f"{len(otp_rows)} bản ghi verify-otp, tất cả đều che OTP",
)
print("        Vài dòng gần nhất:")
for r in rows[-5:]:
    print(
        f"        {r[0]:6} {r[1][:46]:46} {r[2]}  {str(r[3] or '-'):7} {r[6]}ms  req={str(r[5])[:10]}"
    )
if otp_rows:
    print("        Payload đã che của verify-otp:")
    print("        " + (otp_rows[0][4] or "")[:150])

print("\n" + "=" * 78)
print(f"  KẾT QUẢ: {sum(results)}/{len(results)} bước đạt")
print("=" * 78)
sys.exit(0 if all(results) else 1)
