import os
from typing import Any, Dict, Iterable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

# HTTPBearer extracts the "Authorization: Bearer <token>" header.
security = HTTPBearer(auto_error=False)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

_supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


ROLE_ALIASES = {
    "student": "STUDENT",
    "staff": "EVALUATOR",
    "evaluator": "EVALUATOR",
    "admin": "ADMIN_COE",
    "admin_coe": "ADMIN_COE",
    "coe": "ADMIN_COE",
    "hod": "HOD_AUDITOR",
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


def _require_supabase() -> Client:
    if _supabase is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CRITICAL: Supabase environment variables are missing.",
        )
    return _supabase


def _resolve_profile(supabase: Client, user_id: str | None) -> Dict[str, Any]:
    if not user_id:
        return {}
    try:
        profile_res = (
            supabase.table("profiles")
            .select("id, full_name, email, department, role")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return profile_res.data or {}
    except Exception:
        return {}


def _audit_unauthorized_attempt(user_id: str | None, action: str, detail: Dict[str, Any]) -> None:
    if not _supabase:
        return

    payload = {
        "actor_id": user_id,
        "action": action,
        "target_id": "API_ENDPOINT",
        "ip_address": "Captured_by_Proxy",
        "details": detail,
    }

    try:
        _supabase.table("institutional_audit_logs").insert(payload).execute()
        return
    except Exception:
        pass

    try:
        _supabase.table("audit_logs").insert(payload).execute()
    except Exception:
        # Logging must never block request lifecycle.
        return


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """Validates JWT through Supabase Auth and normalizes identity payload."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header.",
        )

    supabase = _require_supabase()
    token = credentials.credentials
    try:
        user_response = supabase.auth.get_user(token)
        auth_user = getattr(user_response, "user", None)
        if not auth_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token.",
            )

        user_id = getattr(auth_user, "id", None)
        profile = _resolve_profile(supabase, user_id)
        user_metadata = getattr(auth_user, "user_metadata", {}) or {}
        app_metadata = getattr(auth_user, "app_metadata", {}) or {}

        raw_role = user_metadata.get("role") or app_metadata.get("role") or profile.get("role")
        role = _normalize_role(raw_role)
        email = getattr(auth_user, "email", None) or profile.get("email")

        return {
            "id": user_id,
            "uid": user_id,
            "email": email,
            "role": role,
            "department": user_metadata.get("department") or profile.get("department", ""),
            "full_name": user_metadata.get("full_name") or profile.get("full_name", ""),
            "profile": profile
            or {
                "id": user_id,
                "email": email,
                "role": role,
            },
            "auth_user": auth_user,
            # Compatibility alias for older handlers that expect this key.
            "user": auth_user,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(exc)}",
        )


# Backward-compatible alias used by legacy imports.
verify_user = verify_token


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Compatibility dependency used across backend endpoints."""
    return verify_token(credentials)


def _coerce_allowed_roles(allowed_roles: Iterable[str] | str) -> set[str]:
    if isinstance(allowed_roles, str):
        return {_normalize_role(allowed_roles)}
    return {_normalize_role(role) for role in allowed_roles}


def require_role(*allowed_roles: str):
    """Closure to enforce strict RBAC in dependency-injected routes."""
    if len(allowed_roles) == 1 and isinstance(allowed_roles[0], (list, tuple, set)):
        normalized_allowed = _coerce_allowed_roles(allowed_roles[0])
    else:
        normalized_allowed = _coerce_allowed_roles(allowed_roles)

    def role_checker(user_data: Dict[str, Any] = Depends(verify_token)) -> Dict[str, Any]:
        user_role = user_data.get("role")
        if user_role not in normalized_allowed:
            _audit_unauthorized_attempt(
                user_data.get("id"),
                "UNAUTHORIZED_ACCESS_ATTEMPT",
                {
                    "required_roles": sorted(normalized_allowed),
                    "received_role": user_role,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Absolute Isolation: You do not have the required clearance to access this portal.",
            )
        return user_data

    return role_checker


def require_staff(user: Dict[str, Any] = Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR"))) -> Dict[str, Any]:
    """Guard for staff-only endpoints."""
    return user


def require_subject_allocation(subject_id: str | None = None):
    """Ensure evaluator is allocated to the requested subject/class/semester before allowing access."""

    def allocation_checker(
        request: Request,
        user_data: Dict[str, Any] = Depends(require_role("EVALUATOR")),
    ) -> Dict[str, Any]:
        supabase = _require_supabase()
        user_id = user_data.get("id")
        dynamic_subject_id = subject_id or request.path_params.get("subject_id") or request.query_params.get("subject_id")
        dynamic_class_id = request.path_params.get("class_id") or request.query_params.get("class_id")
        dynamic_semester = request.path_params.get("semester") or request.query_params.get("semester")

        if not dynamic_subject_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject id is required for allocation verification.",
            )

        try:
            query = (
                supabase.table("staff_allocations")
                .select("id")
                .eq("staff_id", user_id)
                .eq("subject_id", dynamic_subject_id)
            )

            if dynamic_class_id:
                query = query.eq("class_id", dynamic_class_id)
            if dynamic_semester:
                query = query.eq("semester", dynamic_semester)

            allocation = query.limit(1).execute()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to verify staff allocation: {str(exc)}",
            )

        if not allocation.data:
            _audit_unauthorized_attempt(
                user_id,
                "SUBJECT_ACCESS_DENIED",
                {"subject_id": dynamic_subject_id},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subject-Locked: You are not assigned to evaluate this subject.",
            )
        return user_data

    return allocation_checker


async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Return decoded user if token exists and is valid; otherwise None."""
    if not credentials:
        return None
    try:
        return verify_token(credentials)
    except HTTPException:
        return None
