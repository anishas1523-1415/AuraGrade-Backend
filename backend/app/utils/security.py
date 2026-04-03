import time
import asyncio
from collections import deque
from typing import Optional, List

from fastapi import HTTPException, Request, Depends
from supabase import Client

from app.dependencies import get_supabase
from app.logging_config import get_logger

logger = get_logger("security_utils")

# In-memory sliding-window limiter
_rate_limit_buckets: dict[str, deque[float]] = {}
_rate_limit_lock = asyncio.Lock()

async def enforce_rate_limit(
    request: Request,
    current_user: dict | None,
    route_key: str,
    max_requests: int = 8,
    window_seconds: int = 60,
) -> None:
    """Enterprise rate limiting for expensive AI endpoints."""
    identity = (
        (current_user or {}).get("id")
        or (current_user or {}).get("email")
        or (request.client.host if request.client else "unknown")
    )
    bucket_key = f"{route_key}:{identity}"
    now = time.time()
    cutoff = now - window_seconds

    async with _rate_limit_lock:
        bucket = _rate_limit_buckets.setdefault(bucket_key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            logger.warning(f"Rate limit exceeded for {identity} on {route_key}")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please wait {window_seconds}s.",
            )

        bucket.append(now)

def is_staff_role(role: str | None) -> bool:
    return (role or "") in {"EVALUATOR", "ADMIN_COE", "HOD_AUDITOR", "PROCTOR"}

def ensure_student_access(current_user: dict, reg_no: str, supabase: Client):
    if is_staff_role(current_user.get("role")):
        return

    email = current_user.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="Access denied")

    student_res = (
        supabase.table("students")
        .select("reg_no")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    linked = (student_res.data or [{}])[0].get("reg_no") if student_res.data else None
    if not linked or linked.upper() != reg_no.upper():
        raise HTTPException(
            status_code=403,
            detail="Student account is not linked to this register number.",
        )

def ensure_grade_access(current_user: dict, grade_row: dict):
    if is_staff_role(current_user.get("role")):
        return

    email = (current_user.get("email") or "").lower().strip()
    student_email = ((grade_row.get("students") or {}).get("email") or "").lower().strip()
    if not email or email != student_email:
        raise HTTPException(status_code=403, detail="Access denied")
