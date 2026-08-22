"""Centralized error handling (spec §31/§45): every error the API returns — expected or
not — comes out shaped as `{"success": false, "error": {"code", "message"}}` and never
leaks an internal stack trace to the client. Raise `AppError` (or one of its factory
classmethods) from anywhere in the app; the handlers registered here do the rest.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """The one exception type application code should raise for expected failures."""

    def __init__(self, message: str, status_code: int = 400, code: str = "BAD_REQUEST"):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)

    @classmethod
    def bad_request(cls, message: str, code: str = "BAD_REQUEST") -> "AppError":
        return cls(message, status.HTTP_400_BAD_REQUEST, code)

    @classmethod
    def unauthorized(cls, message: str = "Authentication required", code: str = "UNAUTHORIZED") -> "AppError":
        return cls(message, status.HTTP_401_UNAUTHORIZED, code)

    @classmethod
    def forbidden(cls, message: str = "You do not have permission to perform this action", code: str = "FORBIDDEN") -> "AppError":
        return cls(message, status.HTTP_403_FORBIDDEN, code)

    @classmethod
    def not_found(cls, message: str, code: str = "NOT_FOUND") -> "AppError":
        return cls(message, status.HTTP_404_NOT_FOUND, code)

    @classmethod
    def conflict(cls, message: str, code: str = "CONFLICT") -> "AppError":
        return cls(message, status.HTTP_409_CONFLICT, code)

    @classmethod
    def too_many_requests(cls, message: str = "Too many requests, please slow down", code: str = "RATE_LIMITED") -> "AppError":
        return cls(message, status.HTTP_429_TOO_MANY_REQUESTS, code)

    @classmethod
    def payment_required(cls, message: str, code: str = "PAYMENT_REQUIRED") -> "AppError":
        return cls(message, status.HTTP_402_PAYMENT_REQUIRED, code)


def _error_body(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        field = ".".join(str(p) for p in first["loc"][1:]) if first else None
        message = f"{field}: {first['msg']}" if first and field else "Invalid request data"
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=_error_body("VALIDATION_ERROR", message))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_body("HTTP_ERROR", str(exc.detail)))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        error_id = uuid.uuid4().hex[:12]
        logger.exception("Unhandled exception [error_id=%s]", error_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", f"Something went wrong. Please try again. (reference: {error_id})"),
        )
