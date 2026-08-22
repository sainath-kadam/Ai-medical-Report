"""Minimal in-process sliding-window rate limiter (spec §31). Deliberately dependency-free
and single-process — correct behavior for local dev / a single container. The seam to
swap in a Redis-backed limiter (needed the moment there is more than one API replica) is
exactly this one class: same interface, backed by `INCR`+`EXPIRE` instead of a dict.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

WINDOW_SECONDS = 15 * 60

# Only the actual credential-guessing-vulnerable endpoints get the tight cap. Authenticated
# auth-utility endpoints (/auth/me, /auth/refresh, /auth/logout, /auth/change-password) are
# called routinely by every normal page load/navigation (see AuthContext.tsx's
# refreshProfile) and must NOT share that budget — a real user browsing the app would
# otherwise eventually exhaust it and get spuriously logged out. This was found by an
# end-to-end browser smoke test: repeated navigation legitimately drove /auth/me into 429,
# which the frontend (before its own fix, see AuthContext.tsx) treated as "not authenticated".
_BRUTE_FORCE_PRONE_PATHS = (
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/google",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _limit_for(self, path: str) -> int:
        if path.startswith(_BRUTE_FORCE_PRONE_PATHS):
            return settings.rate_limit_auth_per_15min
        return settings.rate_limit_api_per_15min

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        is_brute_force_prone = request.url.path.startswith(_BRUTE_FORCE_PRONE_PATHS)
        key = f"{client_ip}:{'auth' if is_brute_force_prone else 'api'}"
        limit = self._limit_for(request.url.path)

        now = time.monotonic()
        window_start = now - WINDOW_SECONDS
        hits = [t for t in self._hits[key] if t > window_start]
        hits.append(now)
        self._hits[key] = hits

        if len(hits) > limit:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": {"code": "RATE_LIMITED", "message": "Too many requests, please slow down"}},
            )
        return await call_next(request)
