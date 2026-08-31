"""Exception nghiệp vụ + handler chuẩn hoá response lỗi."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "app_error"

    def __init__(self, message: str, *, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class InvalidTransitionError(ConflictError):
    """Chuyển trạng thái chuyến không hợp lệ (SPEC 5.1)."""

    code = "invalid_trip_transition"


class FraudRejectedError(AppError):
    """Bị chặn bởi cơ chế chống gian lận (SPEC 7)."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "fraud_rejected"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )
