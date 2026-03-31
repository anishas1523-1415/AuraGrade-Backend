import os
from typing import Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client, create_client

# HTTPBearer extracts the "Authorization: Bearer <token>" header.
security = HTTPBearer(auto_error=False)
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


ROLE_ALIASES = {
    "student": "STUDENT",
    "staff": "EVALUATOR",
    "evaluator": "EVALUATOR",
    "admin": "ADMIN_COE",
    "admin_coe": "ADMIN_COE",
    "hod_auditor": "HOD_AUDITOR",
    "proctor": "PROCTOR",
}


def _normalize_role(raw_role: str | None) -> str:
    role = (raw_role or "student").strip()
    if not role:
        return "STUDENT"

    lowered = role.lower()
    if lowered in ROLE_ALIASES:
        return ROLE_ALIASES[lowered]

    return role.upper()


def verify_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict:
    """Decode Supabase JWT using shared JWT secret and return normalized user identity."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    if not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server Configuration Error: Missing JWT Secret",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )

        user_id = payload.get("sub")
        user_metadata = payload.get("user_metadata", {}) or {}
        app_metadata = payload.get("app_metadata", {}) or {}
        profile = None
        raw_role = user_metadata.get("role") or app_metadata.get("role")

        # Compatibility fallback: existing AuraGrade deployments store role in profiles.
        if _supabase and user_id:
            try:
                profile_res = (
                    _supabase.table("profiles")
                    .select("id, full_name, email, department, role")
                    .eq("id", user_id)
                    .single()
                    .execute()
                )
                profile = profile_res.data or None
                if profile and not raw_role:
                    raw_role = profile.get("role")
            except Exception:
                profile = None

        user_role = _normalize_role(raw_role)

        full_name = user_metadata.get("full_name") or (profile or {}).get("full_name", "")
        department = user_metadata.get("department") or (profile or {}).get("department", "")
        email = payload.get("email") or (profile or {}).get("email")

        return {
            "id": user_id,
            "uid": user_id,
            "role": user_role,
            "email": email,
            "full_name": full_name,
            "department": department,
            "profile": profile or {
                "id": user_id,
                "email": email,
                "role": user_role,
            },
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


def require_staff(user: dict = Depends(verify_user)) -> Dict:
    """Guard for staff-only endpoints."""
    allowed_roles = ["EVALUATOR", "ADMIN_COE", "HOD_AUDITOR"]
    if user.get("role") not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Institutional access denied. Insufficient permissions.",
        )
    return user


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Compatibility dependency used across backend endpoints."""
    return verify_user(credentials)


def require_role(*allowed_roles: str):
    """Compatibility RBAC dependency factory with normalized roles."""
    normalized_allowed = {_normalize_role(role) for role in allowed_roles}

    async def _check_role(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ):
        user = verify_user(credentials)
        if user.get("role") not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role: {' or '.join(sorted(normalized_allowed))}. "
                    f"Your role: {user.get('role', 'UNKNOWN')}"
                ),
            )
        return user

    return _check_role


async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Return decoded user if token exists and is valid; otherwise None."""
    if not credentials:
        return None
    try:
        return verify_user(credentials)
    except HTTPException:
        return None
