"""
AuraGrade — Backend Authentication & RBAC Guard
================================================
Verifies Supabase JWT tokens and enforces role-based access.

Usage in endpoints:
    from auth_guard import require_auth, require_role

    @app.get("/api/admin/stats")
    async def admin_stats(user = Depends(require_role("ADMIN_COE"))):
        ...

    @app.get("/api/grades")
    async def list_grades(user = Depends(require_auth)):
        ...
"""

import os
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client

# ─── Supabase Admin Client (Service Role) ─────────────────────
_supabase_url = os.environ.get("SUPABASE_URL", "")
_supabase_key = os.environ.get("SUPABASE_KEY", "")
_supabase: Optional[Client] = None

if _supabase_url and _supabase_key:
    _supabase = create_client(_supabase_url, _supabase_key)

# ─── Bearer Token Extractor ───────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


# ─── Core: Verify JWT & Return User ───────────────────────────
async def _get_user_from_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    Extract and verify the Supabase JWT from the Authorization header.
    Returns dict with user info + profile (role, department).
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not _supabase:
        raise HTTPException(status_code=503, detail="Auth service not configured")

    token = credentials.credentials

    try:
        # Supabase's get_user() validates the JWT server-side
        user_response = _supabase.auth.get_user(token)
        user = user_response.user

        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Fetch the user's profile (role, department)
        profile = None
        try:
            result = (
                _supabase.table("profiles")
                .select("id, full_name, email, department, role")
                .eq("id", user.id)
                .single()
                .execute()
            )
            profile = result.data
        except Exception:
            pass

        return {
            "id": user.id,
            "email": user.email,
            "full_name": profile.get("full_name", "") if profile else "",
            "department": profile.get("department", "") if profile else "",
            "role": profile.get("role", "EVALUATOR") if profile else "EVALUATOR",
            "profile": profile,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}",
        )


# ─── Public Dependencies ──────────────────────────────────────

async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    Dependency: Requires any authenticated user.
    Usage: user = Depends(require_auth)
    """
    return await _get_user_from_token(credentials)


def require_role(*allowed_roles: str):
    """
    Dependency factory: Requires the user to have one of the specified roles.

    Usage:
        @app.post("/api/assessments/{id}/lock")
        async def lock(user = Depends(require_role("ADMIN_COE"))):
            ...

        @app.get("/api/grades")
        async def grades(user = Depends(require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR"))):
            ...
    """

    async def _check_role(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    ):
        user = await _get_user_from_token(credentials)
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {' or '.join(allowed_roles)}. Your role: {user['role']}",
            )
        return user

    return _check_role


# ─── Optional Auth (doesn't block, returns None if no token) ──

async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    Dependency: Returns user if authenticated, None otherwise.
    Useful for endpoints that work with or without auth.
    """
    if not credentials:
        return None
    try:
        return await _get_user_from_token(credentials)
    except HTTPException:
        return None
