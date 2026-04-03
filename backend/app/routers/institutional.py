from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import get_supabase
from app.logging_config import get_logger
from auth_guard import require_role, require_subject_allocation

router = APIRouter(prefix="/api", tags=["Institutional Portals"])
logger = get_logger("institutional_router")


class AllocateStaffBody(BaseModel):
    staff_id: str | None = Field(default=None)
    staff_email: str = Field(..., min_length=3)
    subject_id: str = Field(..., min_length=1)
    class_id: str = Field(..., min_length=1)
    semester: str = Field(..., min_length=1)
    department: str | None = Field(default=None)


class ManageProfileBody(BaseModel):
    full_name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    department: str | None = Field(default=None)
    role: str = Field(..., min_length=3)


def _read_audit_activity(supabase: Client) -> List[Dict[str, Any]]:
    try:
        res = (
            supabase.table("institutional_audit_logs")
            .select("id, actor_id, action, created_at")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return res.data or []
    except Exception:
        try:
            res = (
                supabase.table("audit_logs")
                .select("id, actor_id, action, created_at")
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )
            return res.data or []
        except Exception:
            return []


@router.get("/coe/global-analytics")
async def get_global_analytics(
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """Institution-wide metrics for the COE control dashboard."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        grades_res = supabase.table("grades").select("id, ai_score, confidence, is_flagged, prof_status, assessment_id").execute()
        allocations_res = supabase.table("staff_allocations").select("id, staff_email, subject_id, class_id, semester").execute()
        assessments_res = supabase.table("assessments").select("id, subject, title, department, class_id, semester").execute()

        grades = grades_res.data or []
        pass_count = 0
        fail_count = 0
        for row in grades:
            scored = float(row.get("ai_score") or 0)
            if scored >= 4:
                pass_count += 1
            else:
                fail_count += 1

        return {
            "status": "success",
            "data": {
                "exam_configurations": len(assessments_res.data or []),
                "overall_performance": {
                    "total_graded": len(grades),
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                },
                "allocation_count": len(allocations_res.data or []),
                "evaluator_activity_logs": _read_audit_activity(supabase),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"COE analytics fetch failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch global analytics")


@router.get("/hod/department-stats")
async def get_department_stats(
    supabase: Client = Depends(get_supabase),
    user_data=Depends(require_role("HOD_AUDITOR")),
):
    """Department-scoped analytics for the HOD portal."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    department = user_data.get("department") or (user_data.get("profile") or {}).get("department") or ""

    try:
        assessments_res = supabase.table("assessments").select("id, subject, title, department, class_id, semester, staff_email").execute()
        grades_res = supabase.table("grades").select("id, ai_score, confidence, is_flagged, prof_status, assessment_id, student_id, graded_at").execute()
        allocations_res = supabase.table("staff_allocations").select("staff_email, subject_id, class_id, semester, department, is_active").execute()
    except Exception as exc:
        logger.error(f"HOD department stats query failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch department analytics")

    assessments = assessments_res.data or []
    grades = grades_res.data or []
    allocations = allocations_res.data or []

    assessment_map: Dict[str, Dict[str, Any]] = {}
    for assessment in assessments:
        assessment_id = str(assessment.get("id") or "")
        if not assessment_id:
            continue
        assessment_map[assessment_id] = assessment

    subject_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "subject": "UNKNOWN",
        "class_id": "",
        "semester": "",
        "staff_email": "",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "avg_score": 0.0,
        "score_total": 0.0,
    })

    staff_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "staff_email": "",
        "subject_count": 0,
        "student_count": 0,
        "pass_count": 0,
        "fail_count": 0,
        "avg_score": 0.0,
        "score_total": 0.0,
    })

    for assessment in assessments:
        assessment_department = (assessment.get("department") or "").strip()
        if department and assessment_department and assessment_department != department:
            continue

        assessment_id = str(assessment.get("id") or "")
        if not assessment_id:
            continue

        grades_for_assessment = [row for row in grades if str(row.get("assessment_id") or "") == assessment_id]
        if not grades_for_assessment:
            continue

        subject_name = assessment.get("subject") or assessment.get("title") or assessment_id
        class_id = str(assessment.get("class_id") or "")
        semester = str(assessment.get("semester") or "")
        staff_email = str(assessment.get("staff_email") or "")
        subject_key = f"{subject_name}|{class_id}|{semester}"

        entry = subject_metrics[subject_key]
        entry["subject"] = subject_name
        entry["class_id"] = class_id
        entry["semester"] = semester
        entry["staff_email"] = staff_email

        for grade in grades_for_assessment:
            score = float(grade.get("ai_score") or 0)
            entry["total"] += 1
            entry["score_total"] += score
            if score >= 4:
                entry["passed"] += 1
            else:
                entry["failed"] += 1

            if staff_email:
                staff_entry = staff_metrics[staff_email]
                staff_entry["staff_email"] = staff_email
                staff_entry["student_count"] += 1
                staff_entry["score_total"] += score
                if score >= 4:
                    staff_entry["pass_count"] += 1
                else:
                    staff_entry["fail_count"] += 1

    lagging_subjects = []
    for _, metrics in subject_metrics.items():
        total = max(metrics["total"], 1)
        fail_rate = metrics["failed"] / total
        metrics["avg_score"] = round(metrics["score_total"] / total, 2)
        if fail_rate >= 0.3:
            lagging_subjects.append({
                "subject": metrics["subject"],
                "class_id": metrics["class_id"],
                "semester": metrics["semester"],
                "staff_email": metrics["staff_email"],
                "pass_count": metrics["passed"],
                "fail_count": metrics["failed"],
                "fail_rate": round(fail_rate, 4),
                "avg_score": metrics["avg_score"],
            })

    lagging_subjects.sort(key=lambda item: item["fail_rate"], reverse=True)

    staff_summary = []
    for email, metrics in staff_metrics.items():
        total = max(metrics["student_count"], 1)
        staff_summary.append({
            "staff_email": email,
            "subject_count": sum(1 for alloc in allocations if alloc.get("staff_email") == email and alloc.get("department") in {"", department}),
            "student_count": metrics["student_count"],
            "pass_count": metrics["pass_count"],
            "fail_count": metrics["fail_count"],
            "avg_score": round(metrics["score_total"] / total, 2),
        })

    return {
        "status": "success",
        "department": department,
        "data": {
            "total_assessments": len(subject_metrics),
            "total_students": len({row.get("student_id") for row in grades if row.get("student_id")}),
            "subject_breakdown": list(subject_metrics.values()),
            "lagging_subjects": lagging_subjects,
            "staff_performance": staff_summary,
            "allocation_count": sum(1 for alloc in allocations if alloc.get("department") in {"", department}),
        },
    }


@router.post("/coe/allocate-staff")
async def allocate_staff(
    body: AllocateStaffBody,
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """COE-only endpoint to map evaluator to subject/class."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        resolved_staff_id = body.staff_id
        if not resolved_staff_id:
            profile_res = (
                supabase.table("profiles")
                .select("id")
                .eq("email", body.staff_email)
                .limit(1)
                .execute()
            )
            profile_row = (profile_res.data or [{}])[0]
            resolved_staff_id = profile_row.get("id")

        if not resolved_staff_id:
            raise HTTPException(status_code=400, detail="Staff email must match an existing profile before allocation.")

        mapped = (
            supabase.table("staff_allocations")
            .upsert(
                {
                    "staff_id": resolved_staff_id,
                    "staff_email": body.staff_email,
                    "subject_id": body.subject_id,
                    "class_id": body.class_id,
                    "semester": body.semester,
                    "department": body.department,
                },
                on_conflict="staff_email,subject_id,class_id,semester",
            )
            .execute()
        )
        return {
            "status": "success",
            "message": "Staff successfully mapped to subject.",
            "data": mapped.data or [],
        }
    except Exception as exc:
        logger.error(f"Staff allocation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to allocate staff")


@router.get("/coe/staff-accounts")
async def list_staff_accounts(
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """COE-only listing of HOD/staff/proctor accounts."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        result = (
            supabase.table("profiles")
            .select("id, full_name, email, department, role, created_at")
            .in_("role", ["HOD_AUDITOR", "EVALUATOR", "PROCTOR"])
            .order("created_at", desc=True)
            .execute()
        )
        return {"status": "success", "data": result.data or []}
    except Exception as exc:
        logger.error(f"Failed to list staff accounts: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch staff accounts")


@router.post("/coe/staff-accounts")
async def create_staff_account(
    body: ManageProfileBody,
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """COE-only account creation in profiles table for staff/HOD/proctor."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    role = body.role.strip().upper()
    if role not in {"HOD_AUDITOR", "EVALUATOR", "PROCTOR"}:
        raise HTTPException(status_code=400, detail="Role must be one of HOD_AUDITOR, EVALUATOR, PROCTOR")

    try:
        auth_users = supabase.auth.admin.list_users()
        matched_user = next((u for u in auth_users if (getattr(u, "email", "") or "").lower() == body.email.lower()), None)
        if not matched_user:
            raise HTTPException(status_code=400, detail="Email must exist in Supabase Auth before profile creation")

        payload = {
            "id": str(getattr(matched_user, "id")),
            "full_name": body.full_name,
            "email": body.email,
            "department": body.department,
            "role": role,
        }
        result = supabase.table("profiles").upsert(payload, on_conflict="id").execute()
        return {"status": "success", "data": result.data or []}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to create staff account profile: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create staff account")


@router.put("/coe/staff-accounts/{profile_id}")
async def update_staff_account(
    profile_id: str,
    body: ManageProfileBody,
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """COE-only profile update for staff/HOD/proctor."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    role = body.role.strip().upper()
    if role not in {"HOD_AUDITOR", "EVALUATOR", "PROCTOR"}:
        raise HTTPException(status_code=400, detail="Role must be one of HOD_AUDITOR, EVALUATOR, PROCTOR")

    try:
        result = (
            supabase.table("profiles")
            .update(
                {
                    "full_name": body.full_name,
                    "email": body.email,
                    "department": body.department,
                    "role": role,
                }
            )
            .eq("id", profile_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"status": "success", "data": result.data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update staff profile {profile_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update staff account")


@router.delete("/coe/staff-accounts/{profile_id}")
async def delete_staff_account(
    profile_id: str,
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """COE-only removal of profile mapping for staff/HOD/proctor."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        existing = (
            supabase.table("profiles")
            .select("id, role")
            .eq("id", profile_id)
            .single()
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        if existing.data.get("role") == "ADMIN_COE":
            raise HTTPException(status_code=400, detail="COE profiles cannot be deleted from this endpoint")

        supabase.table("profiles").delete().eq("id", profile_id).execute()
        supabase.table("staff_allocations").delete().eq("staff_id", profile_id).execute()
        return {"status": "success", "deleted": True, "profile_id": profile_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete staff profile {profile_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete staff account")


@router.get("/hod/lagging-subjects")
async def get_lagging_subjects(
    supabase: Client = Depends(get_supabase),
    user_data=Depends(require_role("HOD_AUDITOR")),
):
    """Department-scoped fail-rate insights for HOD dashboard."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    department = user_data.get("department") or (user_data.get("profile") or {}).get("department")
    try:
        grades_res = supabase.table("grades").select("assessment_id, ai_score, assessments(subject, department)").execute()
        rows = grades_res.data or []
    except Exception as exc:
        logger.error(f"HOD lagging-subjects query failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch department insights")

    by_subject: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"subject": "UNKNOWN", "total": 0, "passed": 0, "failed": 0}
    )

    for row in rows:
        assessment = row.get("assessments") or {}
        if department and assessment.get("department") and assessment.get("department") != department:
            continue
        subject_id = str(row.get("assessment_id") or "unknown")
        subject_name = assessment.get("subject") or subject_id
        entry = by_subject[subject_id]
        entry["subject"] = subject_name

        scored = float(row.get("ai_score") or 0)

        entry["total"] += 1
        if scored >= 4:
            entry["passed"] += 1
        else:
            entry["failed"] += 1

    lagging = []
    for subject_id, metrics in by_subject.items():
        total = metrics["total"]
        fail_rate = (metrics["failed"] / total) if total > 0 else 0
        if fail_rate >= 0.3:
            lagging.append(
                {
                    "subject_id": subject_id,
                    "subject": metrics["subject"],
                    "pass_count": metrics["passed"],
                    "fail_count": metrics["failed"],
                    "fail_rate": round(fail_rate, 4),
                }
            )

    lagging.sort(key=lambda item: item["fail_rate"], reverse=True)
    return {
        "status": "success",
        "department": department,
        "data": lagging,
    }


@router.get("/staff/my-allocations")
async def get_staff_subjects(
    supabase: Client = Depends(get_supabase),
    user_data=Depends(require_role("EVALUATOR")),
):
    """Staff allocation list for subject/class selection workflow."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        result = (
            supabase.table("staff_allocations")
            .select("id, subject_id, class_id, created_at")
            .eq("staff_id", user_data.get("id"))
            .order("created_at", desc=True)
            .execute()
        )
        return {"status": "success", "data": result.data or []}
    except Exception as exc:
        logger.error(f"Failed to list evaluator allocations: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch staff allocations")


@router.get("/staff/evaluate/{subject_id}/scripts")
async def get_subject_scripts(
    subject_id: str,
    supabase: Client = Depends(get_supabase),
    user_data=Depends(require_subject_allocation()),
):
    """List answer scripts for an evaluator's allocated subject only."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Keep compatibility across schema variants while preserving subject lock from dependency.
    candidate_tables = ["answer_scripts", "submissions", "scripts"]
    last_error = None
    for table_name in candidate_tables:
        try:
            scripts = (
                supabase.table(table_name)
                .select("*")
                .eq("subject_id", subject_id)
                .order("created_at", desc=True)
                .limit(250)
                .execute()
            )
            return {
                "status": "success",
                "data": scripts.data or [],
                "source_table": table_name,
            }
        except Exception as exc:
            last_error = exc

    logger.error(f"Failed to fetch scripts for subject {subject_id}: {last_error}", exc_info=True)
    raise HTTPException(status_code=500, detail="Unable to fetch scripts for this subject")
