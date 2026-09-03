# GoAn — Nền tảng lái hộ công nghệ

Monorepo cho toàn bộ hệ thống GoAn: một backend duy nhất phục vụ 5 sản phẩm.

## Cấu trúc

```
goan/
├── services/
│   ├── api/                    Backend duy nhất — FastAPI modular monolith  ← NGUỒN SỰ THẬT
│   └── _deprecated-api-v0/     Bản nháp cũ, KHÔNG dùng, sẽ xoá (xem ghi chú bên dưới)
├── apps/
│   ├── customer-web/           Web MVP cho khách
│   └── ops-console/            Console vận hành nội bộ (IAM, duyệt tài xế, tra cứu chuyến)
├── packages/                   api-client, realtime-client, ui, shared (sẽ thêm dần)
├── docs/                       Tài liệu kiến trúc & kế hoạch
└── .github/workflows/          CI
```

Các sản phẩm sẽ bổ sung theo lộ trình: `apps/rider-app`, `apps/driver-app`,
`apps/partner-portal`, `apps/website` — xem `docs/GoAn_Phan_Dinh_He_Thong_va_Kien_Truc_Production.md`.

## Tài liệu

| File | Nội dung |
|---|---|
| `docs/GoAn_Kien_Truc_Ky_Thuat_Va_Ke_Hoach_Trien_Khai.md` | Nghiệp vụ, công thức cước, module backend |
| `docs/GoAn_Thiet_Ke_Luong_Thanh_Toan.md` | Luồng tiền, ký quỹ, đối soát |
| `docs/GoAn_Phan_Dinh_He_Thong_va_Kien_Truc_Production.md` | Phân định 5 sản phẩm, chat/tracking, chuẩn production |
| `docs/GoAn_Project_Tracker.xlsx` | Backlog 125 task, tiến độ theo giai đoạn |

## Chạy backend

```bash
cd services/api
cp .env.example .env
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dev nhanh (SQLite, không cần Postgres):
sed -i '' 's|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:///./goan_dev.db|' .env
redis-server --daemonize yes --port 6379
python -m scripts.init_db && python -m scripts.seed
uvicorn app.main:app --reload --port 8000     # http://localhost:8000/docs

# Đầy đủ (Postgres + PostGIS):
docker compose up -d postgres redis && alembic upgrade head
```

## Chạy thử end-to-end (smoke test)

Kiểm chứng cả hệ thống đang chạy thật, không phải test in-process. QA chạy trước mỗi release.

```bash
# cửa sổ 1 — cần Redis đang chạy
cd services/api && source .venv/bin/activate
uvicorn app.main:app --port 8000

# cửa sổ 2
cd services/api && source .venv/bin/activate
make smoke
```

22 bước: sức khoẻ hệ thống · đăng nhập OTP · báo giá · tài xế lên ca sinh QR · đặt chuyến ·
khử trùng request · ghép chuyến · quét QR sai/đúng · ghi GPS · chốt cước và trích ký quỹ ·
ví · xoay vòng refresh token · chặn spam OTP · audit log che PII.

## Rà soát toàn bộ API (quét ngang)

`make smoke` đi MỘT luồng nghiệp vụ. `make audit` gọi MỌI endpoint ít nhất một lần bằng đúng
vai trò, kèm các trường hợp phải bị từ chối — sai vai trò 403, dữ liệu sai 422, không tồn tại 404.

```bash
cd services/api && source .venv/bin/activate
python -m scripts.create_admin 0900000000 "Quản trị viên"   # chỉ cần lần đầu
make audit
```

62 lời gọi trên 34 đường dẫn. Chạy lại được nhiều lần (tự dọn bộ đếm hạn mức của chính nó).

## Kiểm thử & chất lượng

```bash
cd services/api
pytest -q            # 192 test, không cần Postgres/Redis
ruff check app tests
ruff format --check app tests
mypy app
```

## Console nội bộ (IAM)

Nhân sự nội bộ nằm ở bảng riêng `staff_users`, đăng nhập bằng **email + mật khẩu + TOTP**
(bắt buộc 2FA, phiên 8 giờ, sai 5 lần là khoá). Phân quyền theo `domain:action:scope`; vai trò
chỉ là tập hợp quyền lưu trong DB nên sửa quyền không cần deploy.

```bash
cd services/api
python -m scripts.seed_iam                                  # nạp danh mục quyền + 12 vai trò
python -m scripts.seed_iam admin@goan.vn "Nguyễn Văn A"     # + tạo super_admin đầu tiên
```

Lệnh trên in ra mật khẩu và URI TOTP **đúng một lần**. Quét URI vào Google Authenticator rồi
gọi `POST /api/v1/ops/auth/login`. Không endpoint nào đọc lại được bí mật TOTP.

## Quan sát hệ thống

`/metrics` phơi bày số liệu cho Prometheus (số request, độ trễ, request đang xử lý dở). Nhãn
`path` là **template của route** (`/api/v1/trips/{trip_id}`) chứ không phải đường dẫn thật —
lấy đường dẫn thật thì mỗi UUID thành một chuỗi thời gian và Prometheus chết vì cardinality.

Đặt `METRICS_TOKEN` ở production để chỉ Prometheus scrape được. Trace phân tán và Sentry bật
theo cấu hình, gói nằm riêng ở `services/api/requirements-observability.txt`:

```bash
pip install -r requirements.txt -r requirements-observability.txt
# rồi đặt SENTRY_DSN và/hoặc OTEL_EXPORTER_OTLP_ENDPOINT trong .env
```

Thiếu gói mà vẫn đặt biến môi trường thì app chỉ ghi cảnh báo, không sập.

## Sinh API client cho frontend

Frontend **không viết tay endpoint**. Contract đến từ OpenAPI của backend:

```bash
python3 services/api/scripts/export_openapi.py packages/api-client/openapi.json
```

CI sẽ báo đỏ nếu client và backend lệch nhau.

## Ghi chú về `services/_deprecated-api-v0`

Đây là bản backend đầu tiên (9 endpoint, 1 file test), đã bị `services/api` thay thế hoàn toàn.
Giữ tạm để đối chiếu lịch sử, **không sửa và không import**. Sẽ xoá sau khi `apps/customer-web`
chuyển xong sang API mới.
