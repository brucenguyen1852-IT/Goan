# GoAn Backend (FastAPI)

Backend cho nền tảng lái hộ công nghệ GoAn — modular monolith, Python + FastAPI + PostgreSQL/PostGIS.
Xem thêm tài liệu kiến trúc đầy đủ và thiết kế luồng thanh toán đi kèm để hiểu bối cảnh nghiệp vụ.

## Cấu trúc thư mục

```
app/
  core/          # config, database session, security (JWT, hashing)
  models/        # SQLAlchemy ORM models (nguồn sự thật của schema DB)
  schemas/       # Pydantic request/response schemas
  api/v1/        # REST endpoints, chia theo domain (auth, trips, wallet...)
  services/      # business logic thuần (pricing, matching, wallet, payment adapter)
  workers/       # Celery tasks chạy nền (payout, chống gian lận, notification)
  websockets/    # theo dõi vị trí/trạng thái chuyến real-time
alembic/         # database migrations
tests/           # pytest unit tests
```

## Chạy nhanh (local dev, dùng Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/docs (Swagger UI tự sinh từ FastAPI)
- Sau khi container `db` chạy, tạo bảng lần đầu:

```bash
docker compose exec api alembic revision --autogenerate -m "init schema"
docker compose exec api alembic upgrade head
```

## Chạy không dùng Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Cần PostgreSQL có extension PostGIS + Redis chạy sẵn, khai báo trong .env
uvicorn app.main:app --reload
```

## Chạy test

```bash
pytest
```

## Ghi chú triển khai tiếp theo (chưa có trong skeleton này)

- `app/api/v1/endpoints/drivers.py`, `payments.py`, `partners.py`, `admin.py` — theo đúng
  danh sách module trong tài liệu kiến trúc, chưa viết chi tiết ở bản skeleton này.
- Tích hợp thật với VNPay/MoMo/ZaloPay trong `PaymentGatewayAdapter` (hiện là `MockGatewayAdapter`).
- Tích hợp eKYC provider thật (VNPT/FPT.AI) trong luồng `driver/ekyc/submit`.
- Redis GEO (`GEOADD`/`GEOSEARCH`) cho vị trí tài xế real-time — hiện `matching_service.py`
  minh hoạ query PostGIS fallback, chưa nối Redis GEO.
- Migration Alembic đầu tiên cần chạy `--autogenerate` sau khi cấu hình DB thật (không commit sẵn
  vì phụ thuộc phiên bản PostGIS của môi trường bạn dùng).
