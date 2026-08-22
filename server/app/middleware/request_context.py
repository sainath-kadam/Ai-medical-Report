"""Two small pieces of per-request plumbing:

1. A request-id (for correlating a client-visible error reference with server logs).
2. Capturing client IP / User-Agent onto `request.state`, so `audit_service.log(...)`
   can attach "IP/device metadata where appropriate" (spec §30) without every router
   having to know how to extract it from the raw ASGI scope.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger

logger = get_logger("app.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        request.state.client_ip = request.client.host if request.client else None
        request.state.user_agent = request.headers.get("user-agent")

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-Id"] = request.state.request_id
        logger.info(
            "%s %s -> %s (%sms) [req_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.state.request_id,
        )
        return response
