# GoAn — Nền tảng lái hộ công nghệ

Monorepo cho toàn bộ hệ thống GoAn: một backend duy nhất phục vụ 5 sản phẩm.

## Cấu trúc

```
goan/
├── services/
│   ├── api/                    Backend duy nhất — FastAPI modular monolith  ← NGUỒN SỰ THẬT
│   └── _deprecated-api-v0/     Bản nháp cũ, KHÔNG dùng, sẽ xoá (xem ghi chú bên dưới)
├── apps/
│   └── customer-web/           Web MVP cho khách (đang phải viết lại tầng API)
├── packages/                   api-client, realtime-client, ui, shared (sẽ thêm dần)
├── docs/                       Tài liệu kiến trúc & kế hoạch
└── .github/workflows/          CI
```

Các sản phẩm sẽ bổ sung theo lộ trình: `apps/rider-app`, `apps/driver-app`, `apps/ops-console`,
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
pytest -q            # 51 test, không cần Postgres/Redis
ruff check app tests
ruff format --check app tests
mypy app
```

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
