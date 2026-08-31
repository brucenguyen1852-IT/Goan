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