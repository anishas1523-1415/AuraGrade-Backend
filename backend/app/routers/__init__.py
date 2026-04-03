from .system import router as system_router
from .assessment import router as assessment_router
from .grading import router as grading_router
from .staff import router as staff_router
from .student import router as student_router
from .institutional import router as institutional_router
from .coe_portal import router as coe_portal_router

__all__ = [
	"system_router",
	"assessment_router",
	"grading_router",
	"staff_router",
	"student_router",
	"institutional_router",
	"coe_portal_router",
]
