from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    FastMCP = None


MCP_AVAILABLE = FastMCP is not None
_supabase: Optional[Any] = None
_immutable_ledger: list[dict[str, Any]] = []
_idempotency_cache: dict[str, dict[str, Any]] = {}
_mcp_shared_secret = os.environ.get("MCP_SHARED_SECRET", "").strip()


def set_mcp_supabase_client(client: Optional[Any]) -> None:
    """Inject the shared Supabase client from main app startup."""
    global _supabase
    _supabase = client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_record_payload(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _authorized(auth_token: Optional[str]) -> bool:
    if not _mcp_shared_secret:
        return True
    return bool(auth_token) and auth_token == _mcp_shared_secret


def get_recent_sealed_records(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent sealed records from in-memory ledger cache."""
    safe_limit = max(1, min(int(limit), 100))
    return _immutable_ledger[-safe_limit:]


if MCP_AVAILABLE:
    mcp = FastMCP(name="auragrade-ledger-tools")

    @mcp.tool()
    def fetch_real_rubric(course_code: str, auth_token: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch the most recent rubric for a course from Supabase.

        Uses `assessments.rubric_json` as the canonical source. `course_code`
        is matched against `assessments.subject` (case-insensitive).
        """
        normalized_course = (course_code or "").strip()
        if not _authorized(auth_token):
            return {
                "status": "error",
                "message": "Unauthorized MCP call.",
                "course_code": course_code,
                "rubric": None,
            }

        if not normalized_course:
            return {
                "status": "error",
                "message": "course_code is required.",
                "course_code": course_code,
                "rubric": None,
            }

        if not _supabase:
            return {
                "status": "error",
                "message": "Supabase is not configured.",
                "course_code": normalized_course,
                "rubric": None,
            }

        try:
            result = (
                _supabase.table("assessments")
                .select("id, subject, title, rubric_json, created_at")
                .ilike("subject", f"%{normalized_course}%")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            row = (result.data or [None])[0]
            if not row:
                return {
                    "status": "not_found",
                    "message": "No assessment rubric found for the provided course_code.",
                    "course_code": normalized_course,
                    "rubric": None,
                }

            rubric = row.get("rubric_json")
            if not rubric:
                return {
                    "status": "not_found",
                    "message": "Assessment found, but rubric_json is empty.",
                    "course_code": normalized_course,
                    "assessment": {
                        "id": row.get("id"),
                        "subject": row.get("subject"),
                        "title": row.get("title"),
                        "created_at": row.get("created_at"),
                    },
                    "rubric": None,
                }

            return {
                "status": "success",
                "message": "Rubric fetched from Supabase.",
                "course_code": normalized_course,
                "assessment": {
                    "id": row.get("id"),
                    "subject": row.get("subject"),
                    "title": row.get("title"),
                    "created_at": row.get("created_at"),
                },
                "rubric": rubric,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": "Failed to fetch rubric from Supabase.",
                "course_code": normalized_course,
                "rubric": None,
                "error": str(exc),
            }

    @mcp.tool()
    def seal_grade_to_ledger(
        student_id: str,
        course_code: str,
        final_score: float,
        agent_reasoning: str,
        assessment_id: Optional[str] = None,
        evaluator: str = "AuraGrade-Gemini-3-Flash",
        idempotency_key: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Generate a SHA-256 hash for a finalized grade and store a sealed ledger record.

        Use this after AuraGrade's grading/audit loop has converged.
        """
        if not _authorized(auth_token):
            return {
                "status": "error",
                "message": "Unauthorized MCP call.",
                "transaction_hash": None,
                "persisted_to_supabase": False,
                "supabase_error": None,
            }

        if idempotency_key and idempotency_key in _idempotency_cache:
            cached = _idempotency_cache[idempotency_key]
            return {
                **cached,
                "status": "success",
                "message": "Grade already sealed (idempotent replay).",
                "idempotent_replay": True,
            }

        timestamp = _utc_now_iso()
        record = {
            "student_id": student_id,
            "course_code": course_code,
            "final_score": float(final_score),
            "timestamp": timestamp,
            "evaluator": evaluator,
            "assessment_id": assessment_id,
        }

        crypto_hash = _hash_record_payload(record)
        sealed_record = {
            "hash": crypto_hash,
            "data": record,
            "reasoning_log": agent_reasoning,
        }

        _immutable_ledger.append(sealed_record)

        persisted = False
        persist_error = None

        if _supabase:
            try:
                filename = (
                    f"grade-seal-{idempotency_key}.json"
                    if idempotency_key
                    else f"grade-seal-{student_id}-{timestamp}.json"
                )

                if idempotency_key:
                    existing = (
                        _supabase.table("ledger_hashes")
                        .select("id, sha256_hash")
                        .eq("filename", filename)
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        persisted = True
                        response = {
                            "status": "success",
                            "message": "Grade already sealed in Supabase (idempotent).",
                            "transaction_hash": existing.data[0].get("sha256_hash") or crypto_hash,
                            "persisted_to_supabase": True,
                            "supabase_error": None,
                            "idempotent_replay": True,
                        }
                        if idempotency_key:
                            _idempotency_cache[idempotency_key] = response
                        return response

                row = {
                    "assessment_id": assessment_id,
                    "filename": filename,
                    "format": "json",
                    "sha256_hash": crypto_hash,
                    "record_count": 1,
                    "generated_by": "mcp:seal_grade_to_ledger",
                }
                _supabase.table("ledger_hashes").insert(row).execute()
                persisted = True
            except Exception as exc:
                persist_error = str(exc)

        response = {
            "status": "success",
            "message": "Grade sealed in AuraGrade ledger.",
            "transaction_hash": crypto_hash,
            "persisted_to_supabase": persisted,
            "supabase_error": persist_error,
        }
        if idempotency_key:
            _idempotency_cache[idempotency_key] = response
        return response

    @mcp.tool()
    def recent_sealed_grades(limit: int = 20) -> dict[str, Any]:
        """Return recent in-memory sealed grade hashes for quick inspection."""
        recent = get_recent_sealed_records(limit)
        return {
            "count": len(recent),
            "records": recent,
        }


def create_mcp_asgi_app() -> Optional[Any]:
    """Create an ASGI app from FastMCP, compatible across SDK transport variants."""
    if not MCP_AVAILABLE:
        return None

    for attr in ("sse_app", "streamable_http_app", "app"):
        candidate = getattr(mcp, attr, None)
        if candidate is None:
            continue
        if callable(candidate):
            try:
                return candidate()
            except TypeError:
                return candidate
        return candidate

    return None
