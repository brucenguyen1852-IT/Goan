# GoAn Backend (theo SPEC v1.0)

Backend marketplace 2 phía cho dịch vụ lái hộ: rider có xe — driver lái hộ về nhà.
Triển khai đúng đặc tả `SPEC.md`: FastAPI + PostgreSQL/PostGIS + Redis + Celery, SQLAlchemy 2.0 async,
mọi phép tính tiền dùng `Decimal`.

## Test API bằng Swagger (không cần Postgres)

Chế độ dev nhanh: SQLite + Redis local, Swagger UI ở **http://localhost:8000/docs**.

```bash
cp .env.example .env
sed -i '' 's|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:///./goan_dev.db|' .env
redis-server --daemonize yes --port 6379
source .venv/bin/activate
python -m scripts.init_db     # tạo bảng từ metadata (dev only)
python -m scripts.seed        # 2 rider + 3 driver (đã nạp vào Redis GEO) + 2 partner
uvicorn app.main:app --reload --port 8000
```

Luồng thử trên Swagger:

1. `POST /api/v1/auth/request-otp` với `{"phone": "0901000001"}` → response trả `debug_otp` (chỉ khi `DEBUG=true`).
2. `POST /api/v1/auth/verify-otp` với phone + otp + `"role": "rider"` → copy `access_token`.
3. Bấm **Authorize** (góc phải trên), dán token → mọi endpoint có ổ khoá dùng được.
4. `POST /api/v1/trips` tạo chuyến (tự vào matching, offer gửi cho tài xế gần nhất).
5. Mở tab thứ hai / trình duyệt ẩn danh, đăng nhập tài xế `0902000001` (`role: driver`) →
   `POST /api/v1/matching/trips/{id}/accept`.
6. Rider `POST /trips/{id}/verify-qr` với `qr_token` của tài xế (lấy từ `POST /drivers/me/online`
   hoặc cột `driver_profiles.active_qr_token`) → chuyến vào `in_progress`.
7. Tài xế `POST /trips/{id}/gps-ping` vài điểm rồi `POST /trips/{id}/complete` → xem cước, ký quỹ,
   ví trong response và ở `GET /drivers/me/wallet`, `GET /drivers/me/escrow`.

> Dev mode dùng SQLite nên không có PostGIS; matching vẫn chạy vì vị trí tài xế nằm ở Redis GEO.
> Production dùng lệnh ở mục dưới.

## Chạy nhanh (Postgres + PostGIS)

```bash
cp .env.example .env
docker compose up -d postgres redis
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed          # 2 rider + 3 driver + 2 partner + biểu giá
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Chạy toàn bộ bằng Docker (app + celery worker/beat):

```bash
docker compose up --build
```

Test:

```bash
pytest -q            # không cần Postgres/Redis: test dùng SQLite in-memory
```

## Cấu trúc

```
app/
├── main.py                  FastAPI app, mount router, lifespan, /health
├── config.py                Toàn bộ tham số nghiệp vụ (biểu giá, take-rate, ký quỹ, ngưỡng gian lận)
├── database.py              Async engine + session
├── redis_client.py          Pool Redis + namespace key
├── deps.py                  get_db / get_current_user / get_driver_profile / get_redis
├── core/                    security (JWT, mã hoá CCCD), constants (enum), exceptions, money, geo, logging, middleware
├── domains/
│   ├── auth/                SĐT + OTP (mock qua log), JWT access/refresh
│   ├── users/               Hồ sơ, eKYC, online/offline, QR động, vị trí
│   ├── pricing/             Biểu giá + công thức cước (SPEC 4)
│   ├── trips/               State machine + vòng đời chuyến + chốt tiền (SPEC 5)
│   ├── matching/            Redis GEO, offer/accept, khoá phân tán (SPEC 6)
│   ├── fraud/               4 cơ chế chống gian lận (SPEC 7)
│   ├── escrow/              Ký quỹ luỹ tiến 15% (SPEC 8)
│   ├── payments/            Gateway, ví tài xế, rút tiền, đối soát (SPEC 9)
│   ├── partners/            Nhà hàng/khách sạn/bảo hiểm (SPEC 10)
│   └── notifications/       Đẩy event WS (+ chỗ cắm push/SMS)
├── websocket/               connection_manager (Redis pub/sub), events, /ws
├── integrations/            maps (Haversine fallback), ekyc (mock face-match)
└── workers/                 Celery app + beat tasks
```

## API chính

| Method | Path | Ghi chú |
|---|---|---|
| POST | `/api/v1/auth/request-otp` | OTP in ra log ở môi trường dev |
| POST | `/api/v1/auth/verify-otp` | Đăng ký/đăng nhập, trả access+refresh |
| POST | `/api/v1/pricing/estimate` | Giá ước tính trước khi đặt (SPEC 4.5) |
| POST | `/api/v1/trips` | Rider tạo chuyến, tự động vào luồng matching |
| POST | `/api/v1/trips/{id}/verify-qr` | Rider quét QR tài xế → `qr_verified` → `in_progress` |
| POST | `/api/v1/trips/{id}/complete` | Chốt cước, chống chạy vòng, trích quỹ, cộng ví |
| POST | `/api/v1/trips/{id}/gps-ping` | Ghi GPS (hoặc gửi qua WS) |
| GET | `/api/v1/trips/{id}/gps-history` | Lộ trình cho rider xem lại |
| POST | `/api/v1/matching/trips/{id}/accept` | Tài xế nhận chuyến (fallback HTTP của WS) |
| GET | `/api/v1/matching/heatmap` | Gợi ý vị trí trực vệ tinh |
| POST | `/api/v1/drivers/me/online` \| `/offline` | Bật/tắt nhận chuyến, sinh QR động mỗi phiên |
| POST | `/api/v1/drivers/me/selfie-check` | Selfie ngẫu nhiên chống tráo tài xế |
| GET | `/api/v1/drivers/me/escrow` | Số dư + lịch sử ký quỹ |
| POST | `/api/v1/drivers/{id}/escrow/request-refund` | Hoàn quỹ khi ngưng hợp tác (45 ngày) |
| GET/POST | `/api/v1/drivers/me/wallet`, `/drivers/{id}/wallet/withdraw` | Ví và rút tiền |
| GET | `/api/v1/partners/qr/{token}` | Public — đặt xe tại bàn nhà hàng |
| GET/POST | `/api/v1/admin/fraud/*`, `/api/v1/admin/reconciliation*` | Admin |
| WS | `/ws?token=<access_token>` | `location_update`, `trip_offer_response` |

## Quy tắc nghiệp vụ đã cài đặt

**Cước (SPEC 4)** — biểu giá cứng theo deck, override được qua bảng `pricing_rules`:

| | Giờ thường 06–21h | Giờ đêm 21–05h | Cao điểm |
|---|---|---|---|
| Phí nền | 30.000 | 30.000 | 30.000 |
| /km | 20.000 | 24.000 | 27.000 |
| /phút | 500 | 600 | 700 |
| Cước tối thiểu | 100.000 | 110.000 | 120.000 |

- `time_band` chốt tại thời điểm request, tính theo giờ `Asia/Ho_Chi_Minh`.
- Đón xa > 5km: +20.000đ, **100% về tài xế**, không chia take-rate.
- Tài xế nhận 58% phần cước (ngoài phụ thu); take-rate nền tảng 38%; phí thanh toán 2% và phí
  bảo hiểm 5–8% được trừ **trong** phần nền tảng giữ.

**Chống gian lận (SPEC 7)**

| Hành vi | Xử lý trong code |
|---|---|
| Đơn ma | `in_progress` chỉ đến được từ `qr_verified`; QR động đổi mỗi phiên online. Kết thúc chuyến khi chưa quét QR → khoá tài khoản + giữ quỹ |
| Chạy vòng | Cước bị cap ở `optimal × 1.5`; phạt = phần vượt × đơn giá/km × 2, trừ thẳng ký quỹ |
| Thanh toán ngoài app | Cron so tỷ lệ giờ online/đơn với trung bình hệ thống → chỉ **flag** vào `fraud_review_queue`; admin xác nhận mới cảnh cáo/khoá, chuyến liên quan `insurance_voided = true` |
| Tráo tài xế | Selfie ngẫu nhiên 30–90 phút/phiên, face-match < 0.85 → khoá ngay + giữ toàn bộ ký quỹ |

**Ký quỹ (SPEC 8)** — tài xế không đóng tiền trước. Mỗi chuyến trích **15% của `driver_payout`**
(không phải 15% tổng cước) tới khi đạt `escrow_target` (mặc định 3.000.000đ) thì `fulfilled` và
nhận full payout. Phạt gian lận cho phép âm số dư (ghi nhận công nợ, không chặn transaction).
Hoàn quỹ chỉ khi tài xế ngưng hợp tác, chi trả sau 45 ngày qua Celery beat.

> Quỹ là **tài sản của tài xế** và phải được quản lý tách bạch tại một tài khoản ngân hàng riêng
> (ngoài phạm vi code). Bảng `escrow_transactions` giữ audit trail đầy đủ để đối soát với ngân hàng.

**Đối soát (SPEC 9.1)** — job hàng ngày tổng hợp `trips.completed`, so `final_fare` với `payments`,
so `driver_payout` với `wallet_transactions + escrow accrual`, ghi `reconciliation_reports`.

## Job nền (Celery beat)

| Task | Lịch | Việc |
|---|---|---|
| `release_wallet_pending` | mỗi 15 phút | pending → available sau 24h giữ tiền |
| `expire_stale_matching` | mỗi 60s | chuyến quá 90s không ai nhận → `no_driver_found` |
| `daily_reconciliation` | 01:00 UTC | đối soát ngày hôm trước |
| `scan_off_app_signals` | 02:00 UTC | quét tỷ lệ online/đơn bất thường |
| `process_escrow_refunds` | 03:00 UTC | chi trả hoàn ký quỹ đến hạn |

## Phần mock cần thay khi rời MVP

| Thành phần | File | Trạng thái |
|---|---|---|
| Cổng thanh toán | `domains/payments/gateway.py` | `MockPaymentGateway` chạy; `VNPayGateway` là stub |
| eKYC / face-match | `integrations/ekyc.py` | mock deterministic, threshold 0.85 |
| Maps Directions | `integrations/maps.py` | Haversine × 1.3; `GoogleMapsProvider` là stub |
| Hoá đơn VAT | `domains/partners/invoice.py` | mock số hoá đơn |
| SMS OTP | `domains/auth/service.py` | in ra log khi `DEBUG=true` |

## Trạng thái theo Phase (SPEC 12)

- Phase 0 nền tảng, 1 pricing, 2 trips, 3 matching, 4 fraud+escrow, 5 payments, 6 partners,
  7 hardening (rate limit, JSON log, `/health`) — đã cài đặt.
- Test tự động: pricing, state machine, escrow, fraud, luồng chuyến, ví/đối soát.
