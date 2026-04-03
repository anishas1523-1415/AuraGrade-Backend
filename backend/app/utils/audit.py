from typing import Optional, Dict, Any
from supabase import Client
from app.logging_config import get_logger

logger = get_logger("audit")

def log_audit(
    supabase: Client,
    grade_id: str,
    action: str,
    reason: str,
    old_score: float = None,
    new_score: float = None,
    changed_by: str = "system",
    metadata: Dict[str, Any] = None,
):
    """Insert a row into audit_logs. Non-blocking with explicit failure logging."""
    if not supabase:
        logger.warning(f"Audit log skipped for {grade_id} (Supabase not initialized)")
        return
    try:
        supabase.table("audit_logs").insert({
            "grade_id": grade_id,
            "action": action,
            "changed_by": changed_by,
            "old_score": old_score,
            "new_score": new_score,
            "reason": reason,
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        logger.error(f"⚠️ AUDIT LOG FAILURE for grade_id={grade_id}, action={action}: {e}")
        # In production this should fire an alert to a monitoring system
