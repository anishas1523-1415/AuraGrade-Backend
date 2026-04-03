from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.dependencies import get_supabase
from app.logging_config import get_logger
from app.utils.security import ensure_student_access
from auth_guard import require_auth

router = APIRouter(prefix="/api", tags=["Student Ops"])
logger = get_logger("student_router")

@router.get("/students/{reg_no}")
@router.get("/students/{reg_no}/grades")
@router.get("/results/{reg_no}")
async def get_student_results(
    reg_no: str, 
    supabase: Client = Depends(get_supabase),
    current_user=Depends(require_auth)
):
    """
    Standard student results lookup.
    Fetches the latest grading results for the student's registration number.
    In production, this queries the persistent grades table in Supabase.
    """
    search_reg_no = reg_no.upper()
    ensure_student_access(current_user, search_reg_no, supabase)

    logger.info(f"📱 Result lookup request for {search_reg_no}")

    try:
        # Resolve student ID from reg_no first
        student = (
            supabase.table("students")
            .select("id")
            .eq("reg_no", search_reg_no)
            .single()
            .execute()
        )
        
        if not student.data:
            raise HTTPException(status_code=404, detail=f"No student record found for {search_reg_no}")
            
        student_id = student.data["id"]

        # Fetch latest grade for this student
        grade_res = (
            supabase.table("grades")
            .select("*, assessments(subject, title)")
            .eq("student_id", student_id)
            .order("graded_at", desc=True)
            .limit(1)
            .execute()
        )

        if not grade_res.data:
            raise HTTPException(
                status_code=404,
                detail=f"No IA-1 results found for {search_reg_no}. Your paper may still be under review."
            )

        return {
            "status": "success",
            "message": "Results retrieved successfully.",
            "data": grade_res.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching results for {search_reg_no}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching results.")
