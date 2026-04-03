from typing import Optional, List
from supabase import Client
from app.logging_config import get_logger

logger = get_logger("grading_repo")

class GradingRepository:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_student_id_by_reg(self, reg_no: str) -> Optional[str]:
        try:
            res = self.supabase.table("students").select("id").eq("reg_no", reg_no.upper()).single().execute()
            return res.data["id"] if res.data else None
        except Exception:
            return None

    def save_grade(self, student_reg_no: str, assessment_id: str, results: dict) -> Optional[dict]:
        """Consolidated grade persistence logic. Replaces db.save and save_grade_to_db."""
        student_id = self.get_student_id_by_reg(student_reg_no)
        if not student_id:
            logger.warning(f"Student NOT FOUND in roster: {student_reg_no}")
            return None

        # Clean/Format results for Supabase JSONB
        payload = {
            "student_id": student_id,
            "assessment_id": assessment_id,
            "ai_score": results.get("score", 0),
            "confidence": results.get("confidence", 0),
            "feedback": results.get("feedback", []),
            "prof_status": "Pending",
            "is_flagged": results.get("is_flagged", False)
        }

        try:
            # Check for existing grade to prevent duplicates (idempotency at DB level)
            res = self.supabase.table("grades").insert(payload).execute()
            if res.data:
                logger.info(f"Grade persisted for {student_reg_no} on assessment {assessment_id}")
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to persist grade for {student_reg_no}: {e}")
            return None

    def get_latest_grade(self, reg_no: str) -> Optional[dict]:
        student_id = self.get_student_id_by_reg(reg_no)
        if not student_id:
            return None
        try:
            res = (
                self.supabase.table("grades")
                .select("*, assessments(subject, title)")
                .eq("student_id", student_id)
                .order("graded_at", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None
