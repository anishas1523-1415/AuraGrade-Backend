"""
AuraGrade — Shared FastAPI Dependencies
========================================
Provides dependency-injection for Supabase client, Gemini client,
and other shared resources. Avoids global state and enables testability.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from google import genai
from supabase import Client, create_client

from app.config import get_settings
from app.logging_config import get_logger
from app.repositories.grading_repository import GradingRepository
from app.services.batch_service import BatchService
from fastapi import Depends

logger = get_logger("dependencies")

# ── Singletons ──────────────────────────────────────────────

_supabase_client: Optional[Client] = None
_gemini_client: Optional[genai.Client] = None
_batch_service: Optional[BatchService] = None


def get_supabase() -> Optional[Client]:
    """Get or create the Supabase client singleton."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    settings = get_settings()
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        logger.info("Supabase client initialized")
    else:
        logger.warning("Supabase credentials not configured — running without database")

    return _supabase_client


def get_gemini() -> genai.Client:
    """Get or create the Gemini client singleton."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    settings = get_settings()
    _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    logger.info("Gemini client initialized")
    return _gemini_client


def require_supabase() -> Client:
    """Get Supabase client or raise 503 if not configured."""
    from fastapi import HTTPException

    client = get_supabase()
    if client is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    return client

def get_grading_repo(supabase: Client = Depends(get_supabase)) -> GradingRepository:
    """Dependency injection wrapper for the grading repository."""
    if not supabase:
         from fastapi import HTTPException
         raise HTTPException(status_code=503, detail="Database not configured")
    return GradingRepository(supabase)

def get_batch_service(repo: GradingRepository = Depends(get_grading_repo)) -> BatchService:
    """Get or create the BatchService singleton."""
    global _batch_service
    if _batch_service is not None:
        return _batch_service
    _batch_service = BatchService(repo)
    return _batch_service
