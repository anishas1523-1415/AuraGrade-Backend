"""
AuraGrade — Centralized Configuration via Pydantic Settings
============================================================
Single source of truth for all environment variables, defaults, and
validation. Import `settings` from anywhere in the backend.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed, validated configuration loaded from environment variables."""

    # ─── Supabase ────────────────────────────────────────────
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_KEY: str = Field(..., description="Supabase service-role key")
    SUPABASE_JWT_SECRET: str = Field(..., description="JWT secret for token verification")

    # ─── Gemini AI ───────────────────────────────────────────
    GEMINI_API_KEY: str = Field(..., description="Primary Gemini API key")
    GEMINI_API_KEYS: str = Field("", description="Comma-separated extra Gemini keys")
    GEMINI_MODEL: str = Field("gemini-2.5-flash", description="Default Gemini model")

    # ─── CORS ────────────────────────────────────────────────
    CORS_ORIGIN: str = Field("http://localhost:3000", description="Allowed CORS origins (comma-separated)")

    # ─── Optional integrations ───────────────────────────────
    PINECONE_API_KEY: Optional[str] = Field(None, description="Pinecone key for RAG/Sentinel")
    GROQ_API_KEY: Optional[str] = Field(None, description="Groq LLM key (optional)")

    # ─── Rate limiting ───────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = Field(8, description="Max requests per window")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(60, description="Rate limit window in seconds")

    # ─── Grading tuning ──────────────────────────────────────
    HUMAN_REVIEW_CONFIDENCE_THRESHOLD: int = Field(85, ge=0, le=100)
    ALLOWED_SUBJECT_KEYWORDS: str = Field(
        "ai,data science,computer science,cs,python,sql,data structures,algorithms",
        description="Comma-separated allowed subject keywords",
    )

    # ─── Evaluation Flags ────────────────────────────────────
    FAST_EVAL_MODE: bool = Field(True, description="Enable high-speed grading (skips passes)")
    ENABLE_DIAGRAM_PASS: bool = Field(True, description="Enable Pass 0 diagram validation")
    ENABLE_AUDIT_PASS: bool = Field(True, description="Enable Pass 2 professor audit")
    ENABLE_SENTINEL_PASS: bool = Field(True, description="Enable Pass 3 plagiarism/cheat check")
    STAGE_TIMEOUT_SECONDS: int = Field(90, ge=10, le=300)


    # ─── Application ─────────────────────────────────────────
    APP_ENV: str = Field("development", description="Environment: development | staging | production")
    APP_VERSION: str = Field("1.0.0", description="Application version")
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    MAX_UPLOAD_SIZE_MB: int = Field(20, description="Max upload size in MB")

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGIN.split(",") if o.strip()]

    @property
    def allowed_subjects(self) -> List[str]:
        return [s.strip().lower() for s in self.ALLOWED_SUBJECT_KEYWORDS.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"  # Don't fail on unknown env vars


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR / ".env.local")
    return Settings()
