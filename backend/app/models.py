"""
AuraGrade — Pydantic Request/Response Models
=============================================
All request bodies and response schemas centralized here.
Replaces inline model definitions scattered throughout main.py.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── Request Models ──────────────────────────────────────────

class SyncRubricBody(BaseModel):
    rubric_json: dict
    model_text: Optional[str] = None


class CreateAssessmentBody(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=500)


class StrictEvaluateBody(BaseModel):
    student_answer_text: str = Field(..., min_length=1)
    course_rubric: str = Field(..., min_length=1)
    student_id: Optional[str] = None
    course_code: Optional[str] = None
    assessment_id: Optional[str] = None
    agent_reasoning: Optional[str] = None
    evaluator: Optional[str] = "AuraGrade-Gemini-Flash"
    idempotency_key: Optional[str] = None


class CriterionFeedback(BaseModel):
    criterion: str = Field(description="The specific rubric point")
    score_awarded: float = Field(description="Marks given for this criterion")


class EvaluationResult(BaseModel):
    total_score: float = Field(description="The final calculated score out of 10")
    criteria_breakdown: list[CriterionFeedback] = Field(description="Detailed breakdown")
    feedback_trace: str = Field(description="Explanation of marks")
    confidence_score: int = Field(ge=0, le=100, description="Confidence 0-100")


class RegisterDeviceTokenBody(BaseModel):
    push_token: str = Field(..., min_length=10, max_length=500)
    platform: Optional[str] = "android"
    role: Optional[str] = "STUDENT"
    reg_no: Optional[str] = None


class VerifyStudentDobBody(BaseModel):
    dob: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$|^\d{2}[-/\.]\d{2}[-/\.]\d{4}$")


class StudentCreate(BaseModel):
    reg_no: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = None
    course: Optional[str] = "Data Science"


class StudentBulkCreate(BaseModel):
    students: list[StudentCreate] = Field(..., min_length=1, max_length=500)


class ResolveExceptionBody(BaseModel):
    action: str = Field(..., pattern=r"^(RESOLVE|REJECT)$")
    correct_reg_no: Optional[str] = None
    note: Optional[str] = None


class StaffAppealResolveBody(BaseModel):
    new_score: float = Field(..., ge=0)
    professor_notes: str = Field(..., min_length=1, max_length=2000)


# ─── Response Models ─────────────────────────────────────────

class APIResponse(BaseModel):
    """Standard API response envelope."""
    status: str = "success"
    message: Optional[str] = None
    data: Optional[dict] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    request_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    service: str = "auragrade-backend"
    status: str = "healthy"
    version: str = "1.0.0"
    dependencies: dict = {}
