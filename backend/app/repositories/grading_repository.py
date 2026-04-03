from typing import Optional, Tuple

from supabase import Client

from app.logging_config import get_logger

logger = get_logger("grading_repo")


class GradingRepository:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_student_id_by_reg(self, reg_no: str) -> Optional[str]:
        try:
            normalized = (reg_no or "").strip().upper()
            if not normalized:
                return None
            res = (
                self.supabase.table("students")
                .select("id")
                .eq("reg_no", normalized)
                .single()
                .execute()
            )
            return res.data["id"] if res.data else None
        except Exception:
            return None

    def _assessment_exists(self, assessment_id: str) -> bool:
        try:
            res = (
                self.supabase.table("assessments")
                .select("id")
                .eq("id", assessment_id)
                .limit(1)
                .execute()
            )
            return bool(res.data)
        except Exception:
            return False

    def save_grade_with_reason(
        self,
        student_reg_no: str,
        assessment_id: str,
        results: dict,
    ) -> Tuple[Optional[dict], Optional[str]]:
        """Persist or update grade and return a detailed failure reason when unavailable."""
        normalized_assessment_id = (assessment_id or "").strip()
        if not normalized_assessment_id:
            return None, "Assessment not selected"

        student_id = self.get_student_id_by_reg(student_reg_no)
        if not student_id:
            logger.warning(f"Student NOT FOUND in roster: {student_reg_no}")
            return None, "Student register number not found in roster"

        if not self._assessment_exists(normalized_assessment_id):
            logger.warning(f"Assessment NOT FOUND: {normalized_assessment_id}")
            return None, "Assessment mapping missing or invalid"

        raw_score = results.get("score", 0)
        raw_confidence = results.get("confidence", 0)

        try:
            score = float(raw_score or 0)
        except Exception:
            score = 0.0

        try:
            confidence = float(raw_confidence or 0)
        except Exception:
            confidence = 0.0

        # Accept either 0..1 or 0..100 confidence values from model output.
        if confidence > 1:
            confidence = confidence / 100.0
        confidence = max(0.0, min(1.0, confidence))

        payload = {
            "student_id": student_id,
            "assessment_id": normalized_assessment_id,
            "ai_score": score,
            "confidence": confidence,
            "feedback": results.get("feedback", []),
            "prof_status": "Pending",
            "is_flagged": bool(results.get("is_flagged", False)),
        }

        try:
            # Upsert avoids duplicate-row failures for repeated grading on same student+assessment.
            res = self.supabase.table("grades").upsert(
                payload,
                on_conflict="student_id,assessment_id",
            ).execute()
            if res.data:
                row = res.data[0]
                logger.info(f"Grade persisted for {student_reg_no} on assessment {assessment_id}")
                return row, None
            return None, "No data returned after grade upsert"
        except Exception as e:
            logger.error(f"Failed to persist grade for {student_reg_no}: {e}")
            return None, f"Database write failed: {e}"

    def save_grade(self, student_reg_no: str, assessment_id: str, results: dict) -> Optional[dict]:
        """Backward-compatible wrapper used by existing call sites."""
        grade, _ = self.save_grade_with_reason(student_reg_no, assessment_id, results)
        return grade

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
