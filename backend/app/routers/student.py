from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.dependencies import get_supabase
from app.logging_config import get_logger
from app.utils.security import ensure_student_access
from auth_guard import optional_auth

router = APIRouter(prefix="/api", tags=["Student Ops"])
logger = get_logger("student_router")


def _normalize_dob(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("DOB is required")

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    raise ValueError("Invalid DOB format")

@router.get("/students/{reg_no}")
@router.get("/students/{reg_no}/grades")
@router.get("/results/{reg_no}")
async def get_student_results(
    reg_no: str,
    dob: str | None = Query(None),
    supabase: Client = Depends(get_supabase),
    current_user=Depends(optional_auth),
):
    """
    Standard student results lookup.
    Fetches the latest grading results for the student's registration number.
    In production, this queries the persistent grades table in Supabase.
    """
    search_reg_no = reg_no.upper()
    if current_user:
        ensure_student_access(current_user, search_reg_no, supabase)
    elif not dob:
        raise HTTPException(status_code=401, detail="Date of Birth is required.")

    logger.info(f"📱 Result lookup request for {search_reg_no}")

    try:
        # Resolve student ID from reg_no first
        student = (
            supabase.table("students")
            .select("id, reg_no, name, email, dob")
            .eq("reg_no", search_reg_no)
            .single()
            .execute()
        )
        
        if not student.data:
            raise HTTPException(status_code=404, detail=f"No student record found for {search_reg_no}")

        student_row = student.data
        student_id = student_row["id"]

        if not current_user:
            try:
                provided_dob = _normalize_dob(dob or "")
                stored_dob = _normalize_dob(str(student_row.get("dob") or ""))
            except ValueError:
                raise HTTPException(status_code=401, detail="Date of Birth does not match this register number.")

            if provided_dob != stored_dob:
                raise HTTPException(status_code=401, detail="Date of Birth does not match this register number.")

        # Fetch latest grade for this student
        grade_res = (
            supabase.table("grades")
            .select("*, assessments(subject, title)")
            .eq("student_id", student_id)
            .order("graded_at", desc=True)
            .limit(20)
            .execute()
        )

        if not grade_res.data:
            raise HTTPException(
                status_code=404,
                detail=f"No IA-1 results found for {search_reg_no}. Your paper may still be under review."
            )

        grades = grade_res.data or []

        return {
            "status": "success",
            "message": "Results retrieved successfully.",
            "student": {
                "id": student_row.get("id"),
                "reg_no": student_row.get("reg_no"),
                "name": student_row.get("name"),
                "email": student_row.get("email"),
            },
            "grades": grades,
            "data": grades[0],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching results for {search_reg_no}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching results.")
