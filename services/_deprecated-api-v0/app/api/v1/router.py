from fastapi import APIRouter

from app.api.v1.endpoints import auth, trips, wallet

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(trips.router)
api_router.include_router(wallet.router)

# Khi phát triển thêm, gắn nối tiếp tại đây:
# from app.api.v1.endpoints import drivers, payments, partners, admin
# api_router.include_router(drivers.router)
# api_router.include_router(payments.router)
