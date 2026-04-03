from pydantic import BaseModel
from typing import Optional

class ExamState(BaseModel):
    """Holds the currently active rubric extracted from the professor's PDF."""
    active_rubric_json: Optional[dict] = None
    active_rubric_text: Optional[str] = None
    exam_name: str = "Awaiting Setup"
    char_count: int = 0

# Shared state singleton
# In production, this should ideally be moved to a fast-access DB like Redis
# if running in a multi-process/distributed environment.
_state = ExamState()

def get_exam_state() -> ExamState:
    """Get the current global exam state."""
    return _state
