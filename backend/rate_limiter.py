"""
AuraGrade — Rate Limiter
========================
Per-user (JWT sub) rate limiting for AI-expensive endpoints using slowapi.

Usage in main.py:
    from rate_limiter import limiter, rate_limit_handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

Then on each expensive endpoint:
    @limiter.limit("10/minute", key_func=get_user_key)
    @app.post("/api/evaluate")
    async def evaluate_script(request: Request, ...):
"""

import os
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import Request, Response
from fastapi.responses import JSONResponse


def get_user_key(request: Request) -> str:
    """
    Rate limit key: prefer JWT sub (user ID) over IP.
    Falls back to IP if no auth header present.
    This means authenticated users get their own bucket —
    one abusive token can't starve others on the same IP.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        # Extract sub from JWT payload without full verification
        # (verification already happened in require_auth Depends)
        try:
            import base64, json as _json
            parts = token.split(".")
            if len(parts) == 3:
                # Pad base64 to multiple of 4
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub")
                if sub:
                    return f"user:{sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


# Global limiter instance — mounted on app.state in main.py
limiter = Limiter(
    key_func=get_user_key,
    default_limits=[],          # No global default — we set per-route limits
    storage_uri=os.environ.get(
        "RATE_LIMIT_STORAGE_URI",
        "memory://"             # In-memory for single-process; swap for redis:// in prod
    ),
)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return a clean 429 JSON response instead of the default HTML page."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": (
                "Too many requests. AuraGrade AI endpoints are rate-limited "
                "to prevent abuse. Please wait before retrying."
            ),
            "retry_after": str(exc.retry_after) if hasattr(exc, "retry_after") else "60",
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )


# ─── Per-endpoint limit strings ───────────────────────────────────────────────
# These are imported and applied in main.py via @limiter.limit(LIMIT_*)

LIMIT_EVALUATE       = os.environ.get("RL_EVALUATE",       "10/minute")
LIMIT_GRADE_STREAM   = os.environ.get("RL_GRADE_STREAM",   "20/minute")
LIMIT_EVALUATE_SCRIPT= os.environ.get("RL_EVALUATE_SCRIPT","10/minute")
LIMIT_VOICE_RUBRIC   = os.environ.get("RL_VOICE_RUBRIC",   "20/minute")
LIMIT_EVALUATE_BATCH = os.environ.get("RL_EVALUATE_BATCH", "3/minute")
LIMIT_GRADE          = os.environ.get("RL_GRADE",          "20/minute")
LIMIT_RUBRIC_UPLOAD  = os.environ.get("RL_RUBRIC_UPLOAD",  "10/minute")
