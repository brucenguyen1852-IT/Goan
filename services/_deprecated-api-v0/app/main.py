from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.websockets.trip_tracking import router as ws_router

app = FastAPI(
    title=settings.APP_NAME,
    description="GoAn API — Nền tảng dịch vụ lái hộ công nghệ",
    version="0.1.0",
)

# Giai đoạn dev cho phép mọi origin; production PHẢI giới hạn domain thật của app/web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["system"])
def health_check() -> dict:
    return {"status": "ok", "env": settings.APP_ENV}
