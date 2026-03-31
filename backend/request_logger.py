"""
AuraGrade — Structured Request Logger
======================================
FastAPI middleware that:
  1. Generates a unique X-Request-ID per request (UUID4 short)
  2. Logs every request/response with duration, status, and user identity
  3. Propagates the request ID in the response header so frontend can correlate

Mount in main.py:
    from request_logger import RequestLoggerMiddleware
    app.add_middleware(RequestLoggerMiddleware)
"""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("auragrade.access")

# One-time logging config — JSON-style output for log aggregators (Datadog, CloudWatch)
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)


def _extract_user_id(request: Request) -> str:
    """Best-effort user extraction without re-verifying the JWT."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "anonymous"
    try:
        import base64, json as _json
        token = auth[7:]
        parts = token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
            sub = payload.get("sub", "")
            email = payload.get("email", "")
            # Return last 8 chars of sub for partial identity (privacy-safe in logs)
            return f"u:{sub[-8:]}:{email.split('@')[0][:8]}" if sub else "token:invalid"
    except Exception:
        return "token:parse_error"


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate request ID — short UUID is enough for log correlation
        request_id = str(uuid.uuid4())[:12]
        start_time = time.perf_counter()

        # Attach to request state so route handlers can log it
        request.state.request_id = request_id

        user_id = _extract_user_id(request)

        # Process the request
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
            logger.error(
                '"request_id":"%s","method":"%s","path":"%s","user":"%s",'
                '"duration_ms":%s,"error":"%s"',
                request_id, request.method, request.url.path,
                user_id, duration_ms, type(exc).__name__,
            )
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 1)

        # Log at WARNING for 4xx/5xx, INFO for 2xx/3xx
        log_fn = logger.warning if response.status_code >= 400 else logger.info
        log_fn(
            '"request_id":"%s","method":"%s","path":"%s","status":%d,'
            '"user":"%s","duration_ms":%s',
            request_id, request.method, request.url.path,
            response.status_code, user_id, duration_ms,
        )

        # Propagate request ID so frontend/mobile can include it in bug reports
        response.headers["X-Request-ID"] = request_id
        return response
