import os
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.dependencies import get_supabase
from app.logging_config import get_logger
from app.config import get_settings
from app.models import StudentCreate, StudentBulkCreate, ResolveExceptionBody
from app.utils.security import is_staff_role
from auth_guard import require_role, optional_auth

router = APIRouter(prefix="/api", tags=["Staff Ops"])
logger = get_logger("staff_router")

def _is_dev_unauth_allowed() -> bool:
    settings = get_settings()
    bypass_flag = os.getenv("ALLOW_DEV_UNAUTH_CONFIG", "1").strip().lower()
    return (not settings.is_production) and bypass_flag not in {"0", "false", "no", "off"}

def _assert_config_access(current_user: Optional[dict[str, Any]], *allowed_roles: str) -> None:
    if current_user:
        role = (current_user.get("role") or "").upper()
        normalized_allowed = {r.upper() for r in allowed_roles}
        if role in normalized_allowed:
            return
        raise HTTPException(
            status_code=403,
            detail="Absolute Isolation: You do not have the required clearance to access this resource.",
        )

    if _is_dev_unauth_allowed():
        return

    raise HTTPException(status_code=401, detail="Missing authorization header.")

@router.get("/students")
async def list_students(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase),
    current_user = Depends(optional_auth)
):
    """List all students in the roster."""
    _assert_config_access(current_user, "ADMIN_COE", "EVALUATOR", "HOD_AUDITOR")
    result = supabase.table("students").select("*").order("reg_no").range(offset, offset + limit - 1).execute()
    return result.data or []

@router.get("/grades")
async def list_grades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase),
    current_user = Depends(optional_auth)
):
    """Retrieve all graded scripts."""
    _assert_config_access(current_user, "ADMIN_COE", "EVALUATOR", "HOD_AUDITOR")
    result = (
        supabase.table("grades")
        .select("*, assessments(subject, title), students(name, reg_no)")
        .order("graded_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data or []

@router.get("/staff/exceptions")
async def list_exceptions(
    status: Optional[str] = Query("PENDING", description="Filter: PENDING, RESOLVED, REJECTED"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase),
    current_user = Depends(optional_auth),
):
    """List scripts in the exception queue."""
    _assert_config_access(current_user, "ADMIN_COE", "EVALUATOR", "HOD_AUDITOR")
    query = supabase.table("exception_queue").select("*, assessments(subject, title)")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return {
        "status": status,
        "limit": limit,
        "offset": offset,
        "count": len(result.data or []),
        "items": result.data or []
    }

@router.post("/staff/students")
@router.post("/students")
async def create_student(
    body: StudentCreate, 
    supabase: Client = Depends(get_supabase),
    current_user = Depends(optional_auth)
):
    """Add a single student."""
    _assert_config_access(current_user, "ADMIN_COE", "EVALUATOR")
    try:
        result = supabase.table("students").insert({
            "reg_no": body.reg_no,
            "name": body.name,
            "email": body.email,
            "course": body.course,
        }).execute()
        return result.data[0] if result.data else {}
    except Exception as exc:
        logger.error(f"Failed to add student {body.reg_no}: {exc}")
        raise HTTPException(status_code=400, detail="Failed to add student.")

@router.post("/staff/students/bulk")
@router.post("/students/bulk")
async def bulk_create_students(
    body: StudentBulkCreate, 
    supabase: Client = Depends(get_supabase),
    current_user = Depends(optional_auth)
):
    """Bulk upload master roster."""
    _assert_config_access(current_user, "ADMIN_COE", "EVALUATOR")
    rows = [{"reg_no": s.reg_no, "name": s.name, "email": s.email, "course": s.course} for s in body.students]
    try:
        result = supabase.table("students").upsert(rows, on_conflict="reg_no").execute()
        return {"inserted": len(result.data), "count": len(result.data)}
    except Exception as exc:
        logger.error(f"Bulk student import failed: {exc}")
        raise HTTPException(status_code=400, detail="Bulk insert failed.")

@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    supabase: Client = Depends(get_supabase),
    current_user = Depends(optional_auth)
):
    """Retrieve audit logs."""
    _assert_config_access(current_user, "ADMIN_COE", "HOD_AUDITOR")
    result = supabase.table("audit_logs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return {
        "limit": limit,
        "offset": offset,
        "items": result.data or []
    }
