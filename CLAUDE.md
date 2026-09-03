# GoAn — Nền tảng lái hộ công nghệ (Marketplace 2 phía)

## Cấu trúc project

```
~/Developer/goan/
├── goan-backend/          # FastAPI backend (Python)
│   ├── app/
│   │   ├── api/v1/        # REST endpoints: auth, trips, wallet, driver, partner, admin
│   │   ├── models/        # SQLAlchemy ORM: user, trip, wallet, driver, payment, fraud, pricing, partner
│   │   ├── schemas/       # Pydantic request/response
│   │   ├── services/      # Business logic: pricing, wallet, matching, payment, otp
│   │   ├── core/          # Config, database, security (JWT)
│   │   ├── websockets/    # Real-time trip tracking
│   │   └── workers/       # Celery async tasks
│   ├── alembic/           # DB migrations
│   ├── requirements.txt
│   └── docker-compose.yml
│
├── goan-customer-app/     # Web MVP (React + Vite + TypeScript)
│   ├── src/
│   │   ├── pages/         # Login, OTP, Home, TripTracking, History, Profile
│   │   ├── components/    # ui/, layout/, map/
│   │   ├── api/           # Axios API client
│   │   ├── store/         # Zustand state (auth, trip)
│   │   └── hooks/         # WebSocket hook
│   └── package.json
│
├── GoAn_Kien_Truc_Ky_Thuat_Va_Ke_Hoach_Trien_Khai.md
└── GoAn_Thiet_Ke_Luong_Thanh_Toan.md
```

## Chạy local

**Backend:**
```bash
cd ~/Developer/goan/goan-backend
cp .env.example .env
source .venv/bin/activate
# Cần PostgreSQL + Redis chạy sẵn
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd ~/Developer/goan/goan-customer-app
npm run dev
```

## Kiến trúc

- Modular monolith (FastAPI) → microservices khi scale
- PostgreSQL + PostGIS (định vị, điều phối)
- Redis (cache, session, real-time location)
- Celery + RabbitMQ (async jobs: matching, payout)
- WebSocket real-time trip tracking
- Thanh toán: Online (VNPay/MoMo) + Tiền mặt (công nợ tài xế)

## Quy ước làm việc với repo

- **Làm thẳng trên `main`.** Chủ dự án yêu cầu commit xong là push luôn lên `main`, không mở
  nhánh phụ và không chờ merge request (03/09/2026).
- Trước mỗi commit phải xanh: `make -C services/api check` (ruff + mypy + pytest, ngưỡng độ
  phủ 75%). Đổi API thì chạy lại `make -C services/api openapi` và commit `openapi.json`.
- Đổi schema DB thì phải có migration trong `services/api/alembic/versions/`, và `downgrade`
  chạy được.
- Trước mỗi lần phát hành: `make smoke` (một luồng nghiệp vụ đầu-cuối) và `make audit`
  (quét ngang toàn bộ endpoint). Xem `docs/QA/QA_ROLE.md`.

### Lưu ý về việc push

Phiên làm việc của Claude chạy trong một máy ảo tách biệt, **không có thông tin đăng nhập
GitHub** của máy chủ dự án. Claude commit được nhưng không push được. Sau khi Claude báo đã
commit, chạy trên máy:

```bash
cd ~/Developer/goan && git push origin main
```
