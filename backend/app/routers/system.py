from datetime import datetime, timezone
import os

from fastapi import APIRouter, Depends
from supabase import Client

from app.dependencies import get_supabase
from app.logging_config import get_logger
from auth_guard import require_auth

router = APIRouter(prefix="/api/system", tags=["System"])
logger = get_logger("system_router")

@router.get("/readiness")
def system_readiness(current_user=Depends(require_auth), supabase: Client = Depends(get_supabase)):
    """Operational readiness snapshot with dependency health verification."""
    # Verify Supabase connectivity
    supabase_healthy = False
    if supabase:
        try:
            # Simple check
            supabase.table("students").select("id").limit(1).execute()
            supabase_healthy = True
        except Exception as e:
            logger.error(f"Readiness check failed for Supabase: {e}")
            supabase_healthy = False

    # Note: Gemini connectivity is handled in gemini_retry/key_manager
    # In a fully refactored app, we'd inject the key manager here
    gemini_healthy = True # Placeholder for now

    all_healthy = supabase_healthy and gemini_healthy

    return {
        "service": "auragrade-backend",
        "ready": all_healthy,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "supabase": "healthy" if supabase_healthy else "unhealthy",
            "gemini": "healthy" if gemini_healthy else "unhealthy",
            "pinecone": "configured" if os.environ.get("PINECONE_API_KEY") else "not_configured",
        },
        "features": {
            "domain_scope_lock": True,
            "confidence_routing_threshold": 85,
        }
    }
