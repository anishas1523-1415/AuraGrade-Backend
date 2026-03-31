import os
import io
import json
import uuid
import asyncio
import hashlib
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import deque

# Load .env for local development
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local")

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from google import genai
from google.genai import types
from supabase import create_client, Client
from typing import Optional, List, Dict, Any
import base64
from urllib import request as urllib_request

from auth_guard import require_auth, require_role

from evaluator import (
    agentic_grade_stream,
    normalize_grade_result,
    set_gemini_client,
    set_evaluator_supabase,
    upsert_model_answer,
)
from rubric_parser import (
    parse_answer_key_pdf,
    set_parser_client,
    extract_text_from_pdf,
    extract_rubric_from_pdf,
)
from audit_agent import audit_appeal_stream, audit_appeal_sync
from header_parser import (
    identify_student_from_header,
    identify_and_match_student,
    set_header_client,
)
from erp_exporter import (
    generate_university_ledger,
    generate_ledger_preview,
    generate_integrity_hash,
    generate_institutional_ledger,
)
from gap_analysis import (
    generate_class_knowledge_map,
    generate_formatted_knowledge_map,
    compare_assessments,
    update_semantic_gap_data,
    set_gap_client,
)
from vision_logic import (
    detect_diagrams,
    validate_diagram_logic,
    diagram_validation_stream,
    set_vision_client,
)
from similarity_sentinel import (
    check_collusion_risk,
    index_student_submission,
    scan_assessment_collusion,
)
from mcp_tools import (
    create_mcp_asgi_app,
    set_mcp_supabase_client,
    get_recent_sealed_records,
    MCP_AVAILABLE,
)

def _validate_env():
    """Fail fast if critical environment variables are not set."""
    required = {
        "GEMINI_API_KEY": "Required for all AI grading operations",
        "SUPABASE_URL": "Required for database connectivity",
        "SUPABASE_KEY": "Required for database connectivity",
        "SUPABASE_JWT_SECRET": "Required for JWT authentication — CRITICAL security dependency",
    }
    missing = []
    for key, reason in required.items():
        if not os.environ.get(key, "").strip():
            missing.append(f"  • {key}: {reason}")

    if missing:
        print("❌ STARTUP ABORTED — Missing required environment variables:")
        for m in missing:
            print(m)
        print("\nSet these variables in your .env file and restart.")
        sys.exit(1)


_validate_env()

app = FastAPI()

# In-memory sliding-window limiter for expensive AI endpoints.
_rate_limit_buckets: dict[str, deque[float]] = {}
_rate_limit_lock = asyncio.Lock()


async def _enforce_rate_limit(
    request: Request,
    current_user: dict | None,
    route_key: str,
    max_requests: int = 8,
    window_seconds: int = 60,
) -> None:
    identity = (
        (current_user or {}).get("id")
        or (current_user or {}).get("email")
        or (request.client.host if request.client else "unknown")
    )
    bucket_key = f"{route_key}:{identity}"
    now = time.time()
    cutoff = now - window_seconds

    async with _rate_limit_lock:
        bucket = _rate_limit_buckets.setdefault(bucket_key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded for {route_key}. "
                    f"Allowed {max_requests} requests per {window_seconds} seconds."
                ),
            )

        bucket.append(now)

ALLOWED_SUBJECT_KEYWORDS = [
    s.strip().lower()
    for s in os.environ.get(
        "ALLOWED_SUBJECT_KEYWORDS",
        "ai,data science,computer science,cs,python,sql,data structures,algorithms",
    ).split(",")
    if s.strip()
]
GRADE_STREAM_CACHE_MAX = 500
_grade_stream_idempotency_cache: dict[str, dict] = {}
EVALUATE_SSE_CACHE_MAX = 500
_evaluate_sse_idempotency_cache: dict[str, dict] = {}


def _is_allowed_subject(subject: str | None) -> bool:
    value = (subject or "").strip().lower()
    return bool(value) and any(keyword in value for keyword in ALLOWED_SUBJECT_KEYWORDS)


def _ensure_allowed_subject(subject: str | None):
    if not _is_allowed_subject(subject):
        raise HTTPException(
            status_code=422,
            detail=(
                "AuraGrade is currently scope-locked to AI/Data Science/Computer Science assessments. "
                f"Allowed keywords: {', '.join(ALLOWED_SUBJECT_KEYWORDS)}"
            ),
        )


GRADE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "confidence": {"type": "number"},
        "feedback": {"type": "array", "items": {"type": "string"}},
        "is_flagged": {"type": "boolean"},
        "per_question_scores": {"type": "object"},
    },
    "required": ["score", "confidence", "feedback", "is_flagged"],
}

VOICE_RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criteria": {"type": "string"},
                    "max_marks": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["criteria", "max_marks", "description"],
            },
        }
    },
    "required": ["criteria"],
}

STRICT_EVAL_CACHE_MAX = 500
_strict_eval_idempotency_cache: dict[str, dict] = {}


def _send_expo_push(tokens: List[str], title: str, body: str, data: Dict[str, Any] | None = None):
    if not tokens:
        return

    payload = []
    for token in tokens:
        payload.append({
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        })

    req = urllib_request.Request(
        "https://exp.host/--/api/v2/push/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            _ = response.read()
    except Exception as exc:
        print(f"⚠️ Push send failed: {exc}")


def _get_student_push_tokens(student_reg_no: str | None = None):
    if not supabase or not student_reg_no:
        return []

    try:
        tokens_res = (
            supabase.table("device_push_tokens")
            .select("push_token")
            .eq("is_active", True)
            .eq("role", "STUDENT")
            .eq("reg_no", student_reg_no)
            .execute()
        )
        rows = tokens_res.data or []
        return [row["push_token"] for row in rows if row.get("push_token")]
    except Exception as exc:
        print(f"⚠️ Push token lookup failed: {exc}")
        return []


def notify_result_published(student_reg_no: str | None, score: float | None, assessment_id: str | None):
    tokens = _get_student_push_tokens(student_reg_no)
    if not tokens:
        return

    score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "updated"
    _send_expo_push(
        tokens=tokens,
        title="AuraGrade Result Published",
        body=f"Your score is now available: {score_text}",
        data={
            "type": "RESULT_PUBLISHED",
            "reg_no": student_reg_no,
            "assessment_id": assessment_id,
        },
    )


def notify_appeal_resolved(student_reg_no: str | None, new_score: float | None, grade_id: str):
    tokens = _get_student_push_tokens(student_reg_no)
    if not tokens:
        return

    score_text = f"{new_score:.2f}" if isinstance(new_score, (int, float)) else "updated"
    _send_expo_push(
        tokens=tokens,
        title="AuraGrade Appeal Updated",
        body=f"Your appeal was reviewed. New score: {score_text}",
        data={
            "type": "APPEAL_RESOLVED",
            "reg_no": student_reg_no,
            "grade_id": grade_id,
        },
    )

# Enable CORS for your Next.js frontend
_cors_origin = os.environ.get("CORS_ORIGIN", "").strip()
if not _cors_origin:
    # In production this should always be set; warn loudly but don't abort
    print("⚠️  WARNING: CORS_ORIGIN not set. Defaulting to localhost:3000. Set CORS_ORIGIN in production.")
    _cors_origin = "http://localhost:3000"

# Accept comma-separated list for multiple origins
_allowed_origins = [o.strip() for o in _cors_origin.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

# Initialize Gemini 3 Client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
# Share the client with all AI modules
set_gemini_client(client)
set_header_client(client)
set_gap_client(client)
set_vision_client(client)
set_parser_client(client)

# Initialize API key pool for failover
from gemini_retry import init_key_pool
init_key_pool()

# Initialize Supabase Client
supabase_url: str = os.environ.get("SUPABASE_URL", "")
supabase_key: str = os.environ.get("SUPABASE_KEY", "")
supabase: Optional[Client] = None

if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
    set_evaluator_supabase(supabase)  # Share with evaluator for gap analysis post-processing
    print("✅ Supabase connected")
else:
    print("⚠️  Supabase credentials not set — running without database persistence")

# Share Supabase with MCP tool layer (if available)
set_mcp_supabase_client(supabase)

# Mount MCP server transport (SSE/HTTP, SDK-dependent)
mcp_asgi_app = create_mcp_asgi_app()
if mcp_asgi_app:
    app.mount("/mcp", mcp_asgi_app)
    print("✅ MCP tools available at /mcp")
elif not MCP_AVAILABLE:
    print("⚠️  MCP SDK not installed — /mcp endpoint disabled")

# Report Pinecone status
if os.environ.get("PINECONE_API_KEY"):
    print("✅ Pinecone API key detected — RAG enabled")
else:
    print("⚠️  PINECONE_API_KEY not set — RAG disabled (grading still works)")


# ─── Active Exam State (Dynamic Rubric In-Memory Store) ──────
# In production, this lives in Supabase (assessments.rubric_json).
# This in-memory state enables the quick demo flow:
#   1. Professor uploads PDF → /api/setup-exam
#   2. Student papers graded against that PDF automatically

class ExamState:
    """Holds the currently active rubric extracted from the professor's PDF."""
    active_rubric_text: str | None = None
    exam_name: str = "Awaiting Setup"
    char_count: int = 0

state = ExamState()


def _is_staff_role(role: str | None) -> bool:
    return (role or "") in {"EVALUATOR", "ADMIN_COE", "HOD_AUDITOR", "PROCTOR"}


def _ensure_student_access(current_user: dict, reg_no: str):
    if _is_staff_role(current_user.get("role")):
        return

    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    email = current_user.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="Access denied")

    student_res = (
        supabase.table("students")
        .select("reg_no")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    linked = (student_res.data or [{}])[0].get("reg_no") if student_res.data else None
    if not linked or linked.upper() != reg_no.upper():
        raise HTTPException(status_code=403, detail="Access denied")


def _ensure_grade_access(current_user: dict, grade_row: dict):
    if _is_staff_role(current_user.get("role")):
        return

    email = (current_user.get("email") or "").lower().strip()
    student_email = ((grade_row.get("students") or {}).get("email") or "").lower().strip()
    if not email or email != student_email:
        raise HTTPException(status_code=403, detail="Access denied")


# ─── Health Check ─────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"status": "AuraGrade AI Engine is Online. Ready for IA-1 bundles."}


@app.get("/api/system/readiness")
def system_readiness(current_user=Depends(require_auth)):
    """Operational readiness snapshot for deployment and enterprise checks."""
    return {
        "service": "auragrade-backend",
        "ready": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {
            "domain_scope_lock": True,
            "confidence_routing_threshold": int(os.environ.get("HUMAN_REVIEW_CONFIDENCE_THRESHOLD", "85")),
            "mcp_enabled": bool(mcp_asgi_app),
            "supabase_connected": bool(supabase),
            "pinecone_enabled": bool(os.environ.get("PINECONE_API_KEY")),
        },
        "allowed_subject_keywords": ALLOWED_SUBJECT_KEYWORDS,
        "model_config": {
            "primary_model": "gemini-3-flash-preview",
            "structured_json_mode": True,
        },
    }


@app.get("/api/ledger/recent-seals")
def get_recent_mcp_seals(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """REST mirror for recent grade seals emitted via MCP tool calls."""
    records = get_recent_sealed_records(limit)
    return {
        "count": len(records),
        "records": records,
    }


@app.get("/api/auth/me")
async def auth_me(current_user=Depends(require_auth)):
    student = None
    if supabase and current_user.get("email"):
        try:
            student_res = (
                supabase.table("students")
                .select("id, reg_no, name, email, dob")
                .eq("email", current_user["email"])
                .limit(1)
                .execute()
            )
            if student_res.data:
                student = student_res.data[0]
        except Exception:
            student = None

    return {
        "user": {
            "id": current_user.get("id"),
            "email": current_user.get("email"),
            "full_name": current_user.get("full_name"),
            "department": current_user.get("department"),
            "role": current_user.get("role"),
        },
        "student": student,
    }


# ─── Setup Exam: Professor Uploads Answer Key PDF ────────────

@app.post("/api/setup-exam")
async def setup_exam(
    file: UploadFile = File(...),
    current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")),
):
    """
    THE PROFESSOR'S ACTION — Upload a PDF Answer Key / Rubric.

    Receives the PDF, extracts all text using PyMuPDF (fitz),
    and sets it as the active grading standard. Every subsequent
    student paper will be graded against THIS rubric until a new
    one is uploaded.

    This is the first step of the two-step SaaS workflow:
      1. Professor POSTs PDF here → text extracted → stored in state
      2. Student images POSTed to /api/evaluate → graded against that rubric
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported for rubrics. Please upload a .pdf file.",
        )

    try:
        print(f"📥 Received Answer Key PDF: {file.filename}")

        # Read the file directly into memory
        MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB
        pdf_bytes = await file.read()

        if len(pdf_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if len(pdf_bytes) > MAX_PDF_SIZE:
            raise HTTPException(status_code=413, detail=f"PDF exceeds {MAX_PDF_SIZE // (1024*1024)}MB size limit.")

        # Use PyMuPDF extraction (fast & accurate)
        extracted_text = extract_text_from_pdf(pdf_bytes)

        if not extracted_text or len(extracted_text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not extract meaningful text from the PDF. "
                    "If this is a scanned/handwritten PDF, try the /api/rubric/upload-pdf endpoint instead."
                ),
            )

        # Save to global state — the engine is now "armed" with this rubric
        state.active_rubric_text = extracted_text
        state.exam_name = file.filename.replace(".pdf", "")
        state.char_count = len(extracted_text)

        print(f"✅ Active Rubric Updated: {state.exam_name} ({state.char_count} chars)")

        return {
            "status": "success",
            "message": f"Successfully processed {file.filename}. The grading engine is now armed with this rubric.",
            "exam_name": state.exam_name,
            "extracted_character_count": state.char_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error processing rubric: {e}")
        raise HTTPException(status_code=500, detail="Internal error while processing the rubric PDF. Please try again.")


@app.get("/api/exam-state")
async def get_exam_state(current_user=Depends(require_auth)):
    """
    Returns the current active rubric status.
    The frontend uses this to show which exam is currently loaded.
    """
    return {
        "exam_name": state.exam_name,
        "is_active": state.active_rubric_text is not None,
        "character_count": state.char_count,
    }


# ─── Simplified Evaluate Endpoint (SSE) ──────────────────────

@app.post("/api/evaluate")
async def evaluate_script(
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: Optional[str] = Query(None, description="Client-generated idempotency key"),
    current_user=Depends(require_auth),
):
    """
    Simplified SSE endpoint for quick evaluations without student/assessment context.
    Accepts an image upload and streams the full agentic grading pipeline back.

    If a rubric has been uploaded via /api/setup-exam, it will be used as the
    grading standard (closed-book). Otherwise falls back to the default rubric.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    await _enforce_rate_limit(request, current_user, "evaluate", max_requests=6, window_seconds=60)

    idem_key = (idempotency_key or "").strip() or None
    if idem_key and idem_key in _evaluate_sse_idempotency_cache:
        cached = _evaluate_sse_idempotency_cache[idem_key]

        async def replay_generator():
            yield f"event: step\ndata: {json.dumps({'icon': '♻️', 'text': 'Idempotent replay: returning cached evaluation', 'phase': 'idempotent_replay'})}\n\n"
            yield f"event: result\ndata: {json.dumps(cached.get('result', {}))}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'complete', 'idempotent_replay': True})}\n\n"

        return StreamingResponse(
            replay_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    # Fail-safe: don't grade blindly if no rubric is set
    if not state.active_rubric_text:
        raise HTTPException(
            status_code=400,
            detail="No active rubric found. Please upload an Answer Key PDF via /api/setup-exam first.",
        )

    print(f"📥 Received file: {file.filename} ({file.content_type})")
    print(f"📋 Grading against: {state.exam_name} ({state.char_count} chars)")

    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    image_bytes = await file.read()

    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail=f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB size limit.")

    mime_type = file.content_type or "image/jpeg"

    async def event_generator():
        last_result = None
        try:
            # Pass the professor's rubric text into the grading pipeline
            async for event_str in agentic_grade_stream(
                image_bytes,
                mime_type=mime_type,
                dynamic_rubric_text=state.active_rubric_text,
            ):
                yield event_str

                # ── Save final result to MockDatabase ──────────────
                # The SSE stream emits an event like:
                #   event: result\ndata: {"questions": [...], ...}\n\n
                # We parse that final payload and persist it by reg_no
                # so GET /api/results/{reg_no} can serve it instantly.
                if event_str.startswith("event: result"):
                    try:
                        data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                        final_data = json.loads(data_line)
                        last_result = final_data
                        reg = (
                            final_data.get("registration_number")
                            or final_data.get("reg_no")
                            or "UNKNOWN"
                        ).upper()
                        db.save(reg, final_data)
                        print(f"💾 Saved result for {reg} to MockDatabase")
                    except Exception as parse_err:
                        print(f"⚠️  Could not save result to MockDB: {parse_err}")

            if idem_key and last_result:
                if len(_evaluate_sse_idempotency_cache) >= EVALUATE_SSE_CACHE_MAX:
                    _evaluate_sse_idempotency_cache.pop(next(iter(_evaluate_sse_idempotency_cache)))
                _evaluate_sse_idempotency_cache[idem_key] = {"result": last_result}

        except Exception as e:
            print(f"❌ Evaluation Error: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Helper: Route unmatched scripts to Exception Queue ──────
def route_to_exception_queue(
    reg_no: str,
    assessment_id: str | None,
    ai_results: dict,
    reason: str = "Student not found in master roster",
):
    """Insert an unmatched / ghost-student script into the exception queue
    so a human evaluator can resolve it from the Exception Handling Dashboard."""
    if not supabase:
        return None
    try:
        data = {
            "extracted_reg_no": reg_no,
            "extracted_name": ai_results.get("student_name"),
            "assessment_id": assessment_id,
            "ai_score": ai_results.get("score"),
            "confidence": ai_results.get("confidence"),
            "feedback": ai_results.get("feedback", []),
            "reason": reason,
            "status": "PENDING",
        }
        result = supabase.table("exception_queue").insert(data).execute()
        print(f"⚠️  Ghost student '{reg_no}' routed to exception queue")
        return result.data
    except Exception as exc:
        print(f"❌ Failed to route to exception queue: {exc}")
        return None


# ─── Helper: Save grade to Supabase ───────────────────────────
def save_grade_to_db(student_reg_no: str, assessment_id: str, ai_results: dict):
    """Upsert the AI-generated grade into Supabase."""
    if not supabase:
        return None

    # 1. Find the Student UUID from their Reg No
    student = (
        supabase.table("students")
        .select("id")
        .eq("reg_no", student_reg_no)
        .single()
        .execute()
    )

    if not student.data:
        # ── Ghost Student: route to Exception Queue ──
        route_to_exception_queue(
            reg_no=student_reg_no,
            assessment_id=assessment_id,
            ai_results=ai_results,
            reason=f"Registration number '{student_reg_no}' not found in master roster",
        )
        return None

    student_id = student.data["id"]

    # 2. Upsert the AI-generated grade (insert or update on conflict)
    data = {
        "student_id": student_id,
        "assessment_id": assessment_id,
        "ai_score": ai_results["score"],
        "confidence": ai_results["confidence"],
        "feedback": ai_results["feedback"],
        "is_flagged": ai_results.get("is_flagged", False),
        "prof_status": "Flagged" if ai_results.get("human_review_required") else "Pending",
    }

    response = (
        supabase.table("grades")
        .upsert(data, on_conflict="student_id,assessment_id")
        .execute()
    )

    # Ensure we have the grade id — some Supabase/RLS configs
    # return empty data on upsert despite the row being written.
    if response.data and response.data[0].get("id"):
        notify_result_published(
            student_reg_no=student_reg_no,
            score=ai_results.get("score"),
            assessment_id=assessment_id,
        )
        return response.data

    # Fallback: query the grade row we just wrote
    grade = (
        supabase.table("grades")
        .select("id")
        .eq("student_id", student_id)
        .eq("assessment_id", assessment_id)
        .single()
        .execute()
    )
    if grade.data:
        notify_result_published(
            student_reg_no=student_reg_no,
            score=ai_results.get("score"),
            assessment_id=assessment_id,
        )
    return [grade.data] if grade.data else None


# ─── Routes ───────────────────────────────────────────────────

@app.post("/api/grade")
async def grade_paper(
    request: Request,
    file: UploadFile = File(...),
    student_reg_no: Optional[str] = Query(None, description="Student register number"),
    assessment_id: Optional[str] = Query(None, description="Assessment UUID"),
    user=Depends(require_auth),
):
    try:
        await _enforce_rate_limit(request, user, "grade", max_requests=6, window_seconds=60)

        if assessment_id and supabase:
            try:
                assessment_row = (
                    supabase.table("assessments")
                    .select("subject")
                    .eq("id", assessment_id)
                    .single()
                    .execute()
                )
                _ensure_allowed_subject((assessment_row.data or {}).get("subject"))
            except HTTPException:
                raise
            except Exception:
                pass

        # 1. Read the uploaded image
        image_bytes = await file.read()

        # 2. Pre-process image: auto-rotate & enhance
        from image_processor import deskew_and_enhance
        processed_bytes = deskew_and_enhance(image_bytes)

        # 3. Prepare the Multimodal Prompt
        prompt = """
        You are an expert Professor at an AI & Data Science College. 
        IMPORTANT: The image may be rotated or sideways. Rotate your internal
        understanding to read the text horizontally if needed.
        Your task is to grade the provided handwritten answer script based on this Rubric:
        - Conceptual Clarity (4 marks): Does the student understand the core AI concept?
        - Accuracy (4 marks): Are the formulas/definitions correct?
        - Presentation (2 marks): Is the logic structured?

        Output your response strictly in the following JSON format:
        {
            "score": float,
            "confidence": float (0-1),
            "feedback": [
                "point 1",
                "point 2"
            ],
            "is_flagged": boolean (true if handwriting is unreadable or logic is suspicious)
        }
        """

        # 4. Call Gemini 3 Flash (High speed, Multimodal)
        from gemini_retry import call_gemini_async, parse_response
        response = await call_gemini_async(
            client,
            model="gemini-3-flash-preview",
            contents=[
                types.Part.from_bytes(data=processed_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GRADE_RESPONSE_SCHEMA,
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            ),
        )

        # 5. Parse the structured JSON — SAFETY NET
        ai_results = parse_response(response)

        if not ai_results or not isinstance(ai_results, dict):
            # Gemini returned None or non-dict — quota exhausted or parse failure
            ai_results = {
                "score": 0.0,
                "confidence": 0.0,
                "status": "QUOTA_EXHAUSTED",
                "feedback": [
                    "⚠️ API limit reached or image could not be parsed.",
                    "Please wait 60 seconds and try again, or use a clearer image.",
                ],
                "is_flagged": True,
            }

        # Ensure all required keys exist (defensive)
        ai_results.setdefault("score", 0.0)
        ai_results.setdefault("confidence", 0.0)
        ai_results.setdefault("feedback", [])
        ai_results.setdefault("is_flagged", False)
        ai_results.setdefault("per_question_scores", {})
        ai_results = normalize_grade_result(ai_results, default_registration=student_reg_no or "FLAG_FOR_MANUAL")

        # ── DETERMINISTIC MATH: Never trust LLM's total score ─────
        # Use Python arithmetic to sum per-question scores instead of
        # relying on the LLM's self-reported total (prone to hallucination).
        pq = ai_results.get("per_question_scores", {})
        if pq and isinstance(pq, dict):
            calculated_total = round(sum(
                float(v) for v in pq.values() if isinstance(v, (int, float))
            ), 2)
            ai_results["score"] = calculated_total

        # 5. Persist to Supabase if student info is provided
        db_record = None
        if student_reg_no and assessment_id:
            try:
                db_record = save_grade_to_db(student_reg_no, assessment_id, ai_results)
            except Exception:
                db_record = None

        return {
            **ai_results,
            "saved_to_db": db_record is not None,
            "grade_id": db_record[0]["id"] if db_record else None,
        }

    except Exception as e:
        # Never crash the frontend — always return a usable response
        err_msg = str(e)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            return {
                "score": 0.0,
                "confidence": 0.0,
                "confidence_score": 0,
                "human_review_required": True,
                "review_status": "NEEDS_HUMAN_REVIEW",
                "status": "QUOTA_EXHAUSTED",
                "feedback": ["⚠️ API quota full. Please wait 60 seconds and try again."],
                "is_flagged": True,
                "saved_to_db": False,
                "grade_id": None,
            }
        print(f"❌ Grade error (internal): {err_msg}")
        return {
            "score": 0.0,
            "confidence": 0.0,
            "confidence_score": 0,
            "human_review_required": True,
            "review_status": "NEEDS_HUMAN_REVIEW",
            "status": "ERROR",
            "feedback": ["An internal error occurred. Please try again or contact support."],
            "is_flagged": True,
            "saved_to_db": False,
            "grade_id": None,
        }


# ─── NEW: Agentic SSE Streaming Endpoint ─────────────────────

@app.post("/api/grade/stream")
async def grade_paper_stream(
    request: Request,
    file: UploadFile = File(...),
    student_reg_no: Optional[str] = Query(None, description="Student register number"),
    assessment_id: Optional[str] = Query(None, description="Assessment UUID"),
    idempotency_key: Optional[str] = Query(None, description="Client-generated idempotency key"),
    current_user=Depends(require_auth),
):
    """
    Agentic two-pass grading with Server-Sent Events.

    The frontend opens this as an EventSource-compatible stream.
    Events: step, pass1, rag, pass2, result, error, done
    """
    idem_key = (idempotency_key or "").strip() or None
    await _enforce_rate_limit(request, current_user, "grade_stream", max_requests=6, window_seconds=60)
    if idem_key and idem_key in _grade_stream_idempotency_cache:
        cached = _grade_stream_idempotency_cache[idem_key]

        async def replay_generator():
            yield f"event: step\ndata: {json.dumps({'icon': '♻️', 'text': 'Idempotent replay: returning cached grading result', 'phase': 'idempotent_replay'})}\n\n"
            yield f"event: result\ndata: {json.dumps(cached.get('result', {}))}\n\n"
            if cached.get("db"):
                yield f"event: db\ndata: {json.dumps(cached['db'])}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'complete', 'idempotent_replay': True})}\n\n"

        return StreamingResponse(
            replay_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if assessment_id and supabase:
        try:
            assessment_row = (
                supabase.table("assessments")
                .select("subject")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
            _ensure_allowed_subject((assessment_row.data or {}).get("subject"))
        except HTTPException:
            raise
        except Exception:
            pass

    image_bytes = await file.read()

    # Reject excessively large files
    MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds {MAX_IMAGE_SIZE // (1024*1024)}MB limit.",
        )

    # Determine MIME type
    content_type = file.content_type or "image/jpeg"

    # ── PDF-to-Image conversion ────────────────────────────────
    # If the uploaded file is a PDF, convert ALL pages to images
    # and stitch them into one tall JPEG so Gemini sees every page.
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf") or content_type == "application/pdf":
        try:
            import fitz  # PyMuPDF
            import io
            pdf_doc = fitz.open(stream=image_bytes, filetype="pdf")
            n_pages = pdf_doc.page_count
            if n_pages == 0:
                pdf_doc.close()
                raise HTTPException(status_code=400, detail="PDF has no pages")

            # Render each page at 1.5x (faster than 2x, still good for OCR)
            mat = fitz.Matrix(1.5, 1.5)
            page_pixmaps = []
            for i in range(n_pages):
                pix = pdf_doc[i].get_pixmap(matrix=mat)
                page_pixmaps.append(pix)

            if n_pages == 1:
                # Single page — just convert directly
                image_bytes = page_pixmaps[0].tobytes("jpeg")
            else:
                # Multi-page — stitch vertically into one tall image
                import numpy as np
                import cv2
                strips = []
                for pix in page_pixmaps:
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.height, pix.width, pix.n
                    )
                    if pix.n == 4:  # RGBA → BGR
                        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
                    elif pix.n == 3:  # RGB → BGR
                        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    strips.append(img_array)

                # Resize all strips to same width (use the widest)
                max_w = max(s.shape[1] for s in strips)
                resized = []
                for s in strips:
                    if s.shape[1] != max_w:
                        scale = max_w / s.shape[1]
                        s = cv2.resize(s, (max_w, int(s.shape[0] * scale)))
                    resized.append(s)

                stitched = np.vstack(resized)
                # Compress to JPEG (quality 80 for speed)
                _, buf = cv2.imencode(".jpg", stitched, [cv2.IMWRITE_JPEG_QUALITY, 80])
                image_bytes = buf.tobytes()
                print(f"📄 Stitched {n_pages} PDF pages → {len(image_bytes) // 1024}KB image ({stitched.shape[1]}x{stitched.shape[0]})")

            content_type = "image/jpeg"
            pdf_doc.close()
        except HTTPException:
            raise
        except Exception as pdf_exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not convert PDF to image: {str(pdf_exc)[:100]}",
            )

    # Try to load rubric from the assessment in Supabase
    rubric = None
    dynamic_rubric_text = None
    if supabase and assessment_id:
        try:
            row = (
                supabase.table("assessments")
                .select("rubric_json")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
            if row.data and row.data.get("rubric_json"):
                rubric = row.data["rubric_json"]
        except Exception:
            pass  # Fall back to default rubric

    # If no DB rubric found, fall back to the in-memory active rubric
    # (set by /api/setup-exam when professor uploads a PDF)
    if rubric is None and state.active_rubric_text:
        dynamic_rubric_text = state.active_rubric_text

    async def event_generator():
        """Wrap evaluator stream, then persist to DB at the end."""
        final_result = None
        db_payload = None

        async for event_str in agentic_grade_stream(
            image_bytes=image_bytes,
            mime_type=content_type,
            rubric=rubric,
            assessment_id=assessment_id,
            student_reg_no=student_reg_no,
            dynamic_rubric_text=dynamic_rubric_text,
        ):
            # Capture the final result for DB persistence
            if event_str.startswith("event: result"):
                data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                final_result = json.loads(data_line)

            yield event_str

        # After stream completes — persist to Supabase (or emit clear reason)
        if final_result:
            if not student_reg_no and not assessment_id:
                db_payload = {
                    "saved": False,
                    "reason": "Missing student_reg_no and assessment_id",
                }
                yield f"event: db\ndata: {json.dumps(db_payload)}\n\n"
            elif not student_reg_no:
                db_payload = {
                    "saved": False,
                    "reason": "Missing student_reg_no",
                }
                yield f"event: db\ndata: {json.dumps(db_payload)}\n\n"
            elif not assessment_id:
                db_payload = {
                    "saved": False,
                    "reason": "Missing assessment_id",
                }
                yield f"event: db\ndata: {json.dumps(db_payload)}\n\n"
            else:
                try:
                    db_record = save_grade_to_db(
                        student_reg_no, assessment_id, final_result
                    )
                    if db_record:
                        db_payload = {
                            "saved": True,
                            "grade_id": db_record[0]["id"],
                        }
                    else:
                        db_payload = {
                            "saved": False,
                            "reason": "Student not found — routed to Exception Handling Dashboard",
                        }
                    yield f"event: db\ndata: {json.dumps(db_payload)}\n\n"
                except Exception as exc:
                    db_payload = {
                        "saved": False,
                        "reason": str(exc),
                    }
                    yield f"event: db\ndata: {json.dumps(db_payload)}\n\n"

        if idem_key and final_result:
            if len(_grade_stream_idempotency_cache) >= GRADE_STREAM_CACHE_MAX:
                _grade_stream_idempotency_cache.pop(next(iter(_grade_stream_idempotency_cache)))
            _grade_stream_idempotency_cache[idem_key] = {
                "result": final_result,
                "db": db_payload,
            }

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Pydantic models ─────────────────────────────────────────

from pydantic import BaseModel, Field
from typing import Optional as Opt


class SyncRubricBody(BaseModel):
    rubric_json: dict
    model_text: Opt[str] = None


class CreateAssessmentBody(BaseModel):
    subject: str
    title: str


class StrictEvaluateBody(BaseModel):
    student_answer_text: str
    course_rubric: str
    student_id: Opt[str] = None
    course_code: Opt[str] = None
    assessment_id: Opt[str] = None
    agent_reasoning: Opt[str] = None
    evaluator: Opt[str] = "AuraGrade-Gemini-3-Flash"
    idempotency_key: Opt[str] = None


class CriterionFeedback(BaseModel):
    criterion: str = Field(description="The specific rubric point")
    score_awarded: float = Field(description="Marks given for this specific criterion")


class EvaluationResult(BaseModel):
    total_score: float = Field(description="The final calculated score out of 10")
    criteria_breakdown: list[CriterionFeedback] = Field(description="Detailed breakdown of marks")
    feedback_trace: str = Field(description="A concise explanation of why marks were deducted or awarded")
    confidence_score: int = Field(description="An integer from 0 to 100 for confidence")


class RegisterDeviceTokenBody(BaseModel):
    push_token: str
    platform: Opt[str] = "android"
    role: Opt[str] = "STUDENT"
    reg_no: Opt[str] = None


class VerifyStudentDobBody(BaseModel):
    dob: str


def _normalize_dob(value: str | None) -> str | None:
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    normalized = raw.replace("/", "-").replace(".", "-")

    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d")
    except ValueError:
        return None


@app.post("/api/notifications/register-device")
async def register_device_token(body: RegisterDeviceTokenBody, current_user=Depends(require_auth)):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    reg_no = (body.reg_no or "").strip().upper() or None

    if not reg_no and (body.role or "").upper() == "STUDENT" and current_user.get("email"):
        try:
            student_lookup = (
                supabase.table("students")
                .select("reg_no")
                .eq("email", current_user["email"])
                .limit(1)
                .execute()
            )
            if student_lookup.data:
                reg_no = (student_lookup.data[0] or {}).get("reg_no")
        except Exception:
            reg_no = None

    payload = {
        "push_token": body.push_token.strip(),
        "platform": (body.platform or "android").lower(),
        "user_id": current_user.get("id"),
        "email": current_user.get("email"),
        "role": (body.role or "STUDENT").upper(),
        "reg_no": reg_no,
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        supabase.table("device_push_tokens").upsert(payload, on_conflict="push_token").execute()
        return {"status": "ok", "registered": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to register push token: {exc}")


@app.post("/api/auth/verify-student-dob")
async def verify_student_dob(body: VerifyStudentDobBody, current_user=Depends(require_auth)):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    email = (current_user.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Authenticated user email is required")

    student = None
    try:
        student_res = (
            supabase.table("students")
            .select("id, reg_no, name, email, dob")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if student_res.data:
            student = student_res.data[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to verify student record: {exc}")

    if not student:
        return {
            "verified": True,
            "applies_to": "NON_STUDENT",
            "message": "No student record linked to this account",
        }

    entered_dob = _normalize_dob(body.dob)
    if not entered_dob:
        raise HTTPException(status_code=422, detail="DOB must be in YYYY-MM-DD or DD-MM-YYYY format")

    stored_dob = _normalize_dob(student.get("dob"))
    if not stored_dob:
        raise HTTPException(status_code=422, detail="DOB is not configured for this student account")

    if entered_dob != stored_dob:
        raise HTTPException(status_code=401, detail="DOB verification failed")

    return {
        "verified": True,
        "applies_to": "STUDENT",
        "student": {
            "id": student.get("id"),
            "reg_no": student.get("reg_no"),
            "name": student.get("name"),
            "email": student.get("email"),
        },
    }


@app.post("/api/evaluate_script")
async def evaluate_script_strict(
    request: Request,
    body: StrictEvaluateBody,
    current_user=Depends(require_auth),
):
    """
    Strict JSON-mode evaluation endpoint.

    Enforces Gemini structured output via a Pydantic response schema and
    applies confidence routing for enterprise-safe grading.
    """
    if not body.student_answer_text.strip():
        raise HTTPException(status_code=400, detail="student_answer_text is empty")
    if not body.course_rubric.strip():
        raise HTTPException(status_code=400, detail="course_rubric is empty")

    await _enforce_rate_limit(request, current_user, "evaluate_script", max_requests=6, window_seconds=60)

    idem_key = (body.idempotency_key or "").strip() or None
    if idem_key and idem_key in _strict_eval_idempotency_cache:
        return {
            **_strict_eval_idempotency_cache[idem_key],
            "idempotent_replay": True,
        }

    confidence_threshold = int(os.environ.get("HUMAN_REVIEW_CONFIDENCE_THRESHOLD", "85"))

    prompt = f"""
You are an expert AI & Data Science professor grading an exam.
Evaluate the student answer strictly against the provided rubric.

Rubric:
{body.course_rubric}

Student Answer:
{body.student_answer_text}
"""

    try:
        from gemini_retry import call_gemini_async, parse_response

        response = await call_gemini_async(
            client,
            model="gemini-3-flash-preview",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationResult,
                temperature=0.1,
            ),
        )

        result_dict = parse_response(response)
        if not result_dict or not isinstance(result_dict, dict):
            raise HTTPException(status_code=422, detail="Could not parse structured evaluation JSON")

        confidence_score = int(result_dict.get("confidence_score", 100))
        if confidence_score < confidence_threshold:
            response_payload = {
                "status": "NEEDS_HUMAN_REVIEW",
                "message": "Confidence too low to auto-grade.",
                "partial_data": result_dict,
            }
            if idem_key:
                if len(_strict_eval_idempotency_cache) >= STRICT_EVAL_CACHE_MAX:
                    _strict_eval_idempotency_cache.pop(next(iter(_strict_eval_idempotency_cache)))
                _strict_eval_idempotency_cache[idem_key] = response_payload
            return response_payload

        # Seal successful strict evaluation with SHA-256
        seal_payload = {
            "student_id": body.student_id or "UNKNOWN",
            "course_code": body.course_code or "UNSPECIFIED",
            "assessment_id": body.assessment_id,
            "total_score": result_dict.get("total_score"),
            "criteria_breakdown": result_dict.get("criteria_breakdown", []),
            "feedback_trace": result_dict.get("feedback_trace", ""),
            "confidence_score": result_dict.get("confidence_score"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluator": body.evaluator or "AuraGrade-Gemini-3-Flash",
            "agent_reasoning": body.agent_reasoning or "strict-json-evaluation",
        }
        seal_bytes = json.dumps(seal_payload, sort_keys=True).encode("utf-8")
        transaction_hash = generate_integrity_hash(seal_bytes)

        persisted_to_ledger = False
        ledger_error = None

        # Persist to institutional ledger_hashes when assessment_id is available
        if supabase and body.assessment_id:
            try:
                filename = (
                    f"strict-eval-idem-{idem_key}.json"
                    if idem_key
                    else f"strict-eval-{(body.student_id or 'unknown')}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
                )

                if idem_key:
                    existing = (
                        supabase.table("ledger_hashes")
                        .select("sha256_hash")
                        .eq("assessment_id", body.assessment_id)
                        .eq("filename", filename)
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        response_payload = {
                            "status": "SUCCESS",
                            "data": result_dict,
                            "transaction_hash": existing.data[0].get("sha256_hash") or transaction_hash,
                            "sealed_payload": {
                                "student_id": seal_payload["student_id"],
                                "course_code": seal_payload["course_code"],
                                "assessment_id": seal_payload["assessment_id"],
                                "timestamp": seal_payload["timestamp"],
                                "evaluator": seal_payload["evaluator"],
                            },
                            "persisted_to_ledger": True,
                            "ledger_error": None,
                            "idempotent_replay": True,
                        }
                        if idem_key:
                            if len(_strict_eval_idempotency_cache) >= STRICT_EVAL_CACHE_MAX:
                                _strict_eval_idempotency_cache.pop(next(iter(_strict_eval_idempotency_cache)))
                            _strict_eval_idempotency_cache[idem_key] = response_payload
                        return response_payload

                supabase.table("ledger_hashes").insert({
                    "assessment_id": body.assessment_id,
                    "filename": filename,
                    "format": "json",
                    "sha256_hash": transaction_hash,
                    "record_count": 1,
                    "generated_by": "strict_eval_api",
                }).execute()
                persisted_to_ledger = True
            except Exception as exc:
                ledger_error = str(exc)

        response_payload = {
            "status": "SUCCESS",
            "data": result_dict,
            "transaction_hash": transaction_hash,
            "sealed_payload": {
                "student_id": seal_payload["student_id"],
                "course_code": seal_payload["course_code"],
                "assessment_id": seal_payload["assessment_id"],
                "timestamp": seal_payload["timestamp"],
                "evaluator": seal_payload["evaluator"],
            },
            "persisted_to_ledger": persisted_to_ledger,
            "ledger_error": ledger_error,
        }
        if idem_key:
            if len(_strict_eval_idempotency_cache) >= STRICT_EVAL_CACHE_MAX:
                _strict_eval_idempotency_cache.pop(next(iter(_strict_eval_idempotency_cache)))
            _strict_eval_idempotency_cache[idem_key] = response_payload
        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Sync Rubric & Model Answer (Ground Truth) ───────────────

@app.post("/api/sync-rubric")
async def sync_rubric(
    assessment_id: str = Query(..., description="Assessment UUID"),
    body: SyncRubricBody = ...,
    current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")),
):
    """
    Sync rubric JSON and optionally a model-answer text to Supabase + Pinecone.
    Rubric → Supabase assessments.rubric_json
    Model text → Pinecone vector embeddings (RAG anchor)
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    results = []

    # 1. Update rubric_json in Supabase
    try:
        update_data = {"rubric_json": body.rubric_json}
        if body.model_text:
            update_data["model_answer"] = body.model_text

        supabase.table("assessments").update(update_data).eq("id", assessment_id).execute()
        results.append(f"Rubric saved ({len(body.rubric_json)} criteria)")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Supabase update failed: {exc}")

    # 2. If model_text provided, upsert into Pinecone for RAG
    if body.model_text and body.model_text.strip():
        try:
            num_chunks = await upsert_model_answer(assessment_id, body.model_text.strip())
            results.append(f"Model answer indexed — {num_chunks} chunks → Pinecone")
        except RuntimeError as exc:
            results.append(f"Pinecone skipped: {exc}")

    return {
        "status": "success",
        "message": " · ".join(results),
        "assessment_id": assessment_id,
    }


# ─── PDF Answer Key Upload (Dynamic Rubric Pipeline) ─────────

@app.post("/api/rubric/upload-pdf")
async def upload_rubric_pdf(
    file: UploadFile = File(...),
    assessment_id: str = Query(..., description="Assessment UUID to link the rubric to"),
    subject_hint: Optional[str] = Query(None, description="Subject name hint for better parsing"),
    auto_sync: bool = Query(True, description="Automatically sync rubric to Supabase & Pinecone"),
    current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")),
):
    """
    THE DYNAMIC RUBRIC PIPELINE — Faculty uploads a PDF answer key.

    This is the core of the Closed-Book Grading architecture:
    1. Faculty uploads their specific Answer Key / Rubric as PDF
    2. System extracts text (PyPDF2 or Gemini Vision OCR for scanned docs)
    3. Gemini structures it into per-question rubric with mark breakdowns
    4. Rubric JSON → Supabase assessments.rubric_json
    5. Model answer text → Pinecone vector embeddings (RAG anchor)

    After this, AuraGrade grades ONLY based on THIS answer key.
    No web search. No external knowledge. Closed-Book.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    # Accept PDF, images of answer keys, and text files
    content_type = file.content_type or ""
    allowed_types = [
        "application/pdf",
        "image/jpeg", "image/png", "image/webp",
        "text/plain", "text/markdown",
    ]
    if not any(content_type.startswith(t.split('/')[0]) for t in allowed_types) and content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Upload PDF, image, or text file.",
        )

    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if subject_hint:
        _ensure_allowed_subject(subject_hint)

    # If subject_hint not provided, try to get it from the assessment
    if not subject_hint and supabase:
        try:
            row = (
                supabase.table("assessments")
                .select("subject")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
            if row.data:
                subject_hint = row.data.get("subject")
        except Exception:
            pass

    try:
        # Run the full extraction + structuring pipeline
        result = await parse_answer_key_pdf(
            pdf_bytes=pdf_bytes,
            mime_type=content_type,
            subject_hint=subject_hint,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    rubric = result.get("rubric", {})
    model_answer_text = result.get("model_answer_text", "")
    total_marks = result.get("total_marks", 0)
    sync_results = []

    # Auto-sync to Supabase + Pinecone if enabled
    if auto_sync and supabase:
        # 1. Save rubric JSON to Supabase
        try:
            update_data = {"rubric_json": rubric}
            if model_answer_text:
                update_data["model_answer"] = model_answer_text
            supabase.table("assessments").update(update_data).eq("id", assessment_id).execute()
            sync_results.append(f"Rubric saved to Supabase ({len(rubric)} questions, {total_marks} total marks)")
        except Exception as exc:
            sync_results.append(f"Supabase save failed: {exc}")

        # 2. Index model answer in Pinecone for RAG
        if model_answer_text and model_answer_text.strip():
            try:
                num_chunks = await upsert_model_answer(assessment_id, model_answer_text.strip())
                sync_results.append(f"Model answer indexed — {num_chunks} chunks → Pinecone")
            except RuntimeError as exc:
                sync_results.append(f"Pinecone skipped: {exc}")

    return {
        "status": "success",
        "assessment_id": assessment_id,
        "rubric": rubric,
        "total_marks": total_marks,
        "questions_detected": len(rubric),
        "subject_detected": result.get("subject_detected", "Unknown"),
        "exam_type_detected": result.get("exam_type_detected", "Unknown"),
        "extraction_method": result.get("extraction_method", "unknown"),
        "raw_text_length": result.get("raw_text_length", 0),
        "model_answer_available": bool(model_answer_text),
        "sync_results": sync_results,
        "message": (
            f"Answer key parsed: {len(rubric)} questions detected, "
            f"{total_marks} total marks. "
            f"{'Synced to Supabase & Pinecone.' if sync_results else 'Preview only (auto_sync=false).'}"
        ),
    }


# ─── Voice-to-Rubric: Gemini converts teacher's dictation to structured rubric ─

@app.post("/api/voice-to-rubric")
async def voice_to_rubric(
    request: Request,
    transcript: str = Form(...),
    current_user=Depends(require_auth),
):
    """
    Convert a teacher's spoken description into structured rubric JSON.

    The teacher speaks naturally (e.g., "Question 1 is worth 2 marks,
    give 1 mark for the definition and 1 for the example") and Gemini
    structures it into the rubric format used by AuraGrade.
    """
    if not transcript or not transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty")

    await _enforce_rate_limit(request, current_user, "voice_to_rubric", max_requests=5, window_seconds=60)

    prompt = f"""You are a Rubric Structuring Agent for an academic grading system.

A teacher has dictated the following rubric criteria using their voice.
Convert this natural language into a structured JSON rubric.

Teacher's dictation:
\"{transcript}\"

Output ONLY valid JSON in this exact format — no markdown, no extra text:
{{
  "criteria": [
    {{
      "criteria": "<short label for the marking criterion>",
      "max_marks": <integer>,
      "description": "<grading guideline based on what the teacher said>"
    }}
  ]
}}

Rules:
- Extract every distinct question or marking criterion mentioned.
- If the teacher says "Question 1 is worth 5 marks", create an entry with max_marks: 5.
- Combine related sub-points under one criterion when logical.
- Use clear, concise labels (e.g. "Q1: Neural Network Definition").
- If the teacher mentions partial credit rules, include them in the description.
"""

    try:
        from gemini_retry import call_gemini_async, parse_response
        response = await call_gemini_async(
            client,
            model="gemini-2.0-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VOICE_RUBRIC_SCHEMA,
                temperature=0.1,
            ),
        )

        result = parse_response(response)

        if not result or not isinstance(result, dict):
            raise HTTPException(status_code=422, detail="AI could not structure the dictation")

        criteria = result.get("criteria", [])
        return {
            "status": "success",
            "criteria": criteria,
            "questions_detected": len(criteria),
            "total_marks": sum(c.get("max_marks", 0) for c in criteria),
            "transcript": transcript,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Voice-to-rubric conversion failed: {str(exc)[:200]}",
        )


# ─── Create Assessment ───────────────────────────────────────

@app.post("/api/assessments")
async def create_assessment(
    body: CreateAssessmentBody,
    current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")),
):
    """Create a new assessment."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    _ensure_allowed_subject(body.subject)

    result = (
        supabase.table("assessments")
        .insert({"subject": body.subject, "title": body.title})
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create assessment")
    return result.data[0]


# ─── Model Answer Upload (for RAG / Pinecone) ────────────────

@app.post("/api/model-answer")
async def upload_model_answer(
    assessment_id: str = Query(..., description="Assessment UUID to link the model answer to"),
    text: str = Form(None, description="Plain-text model answer"),
    file: Optional[UploadFile] = File(None),
    current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")),
):
    """
    Upload a model answer for an assessment.
    Accepts either plain text via `text` form field, or a text file upload.
    The content is chunked, embedded via Gemini, and upserted into Pinecone.
    """
    content = ""

    if text:
        content = text
    elif file:
        raw = await file.read()
        content = raw.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'text' form field or a file upload",
        )

    if not content.strip():
        raise HTTPException(status_code=400, detail="Model answer content is empty")

    # Also store in Supabase assessments.model_answer column
    if supabase:
        try:
            supabase.table("assessments").update(
                {"model_answer": content}
            ).eq("id", assessment_id).execute()
        except Exception:
            pass  # Non-critical — Pinecone is the primary store

    try:
        num_chunks = await upsert_model_answer(assessment_id, content)
        return {
            "message": f"Model answer indexed — {num_chunks} chunks upserted to Pinecone",
            "assessment_id": assessment_id,
            "chunks": num_chunks,
        }
    except RuntimeError as exc:
        # Pinecone not configured — still saved to Supabase
        return {
            "message": "Model answer saved to Supabase (Pinecone not configured)",
            "assessment_id": assessment_id,
            "pinecone_error": str(exc),
        }


# ─── Students endpoints ──────────────────────────────────────

@app.get("/api/students")
async def list_students(current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR"))):
    """List all students."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = supabase.table("students").select("*").order("reg_no").execute()
    return result.data


@app.get("/api/students/{reg_no}/grades")
async def get_student_grades(
    reg_no: str,
    dob: Optional[str] = Query(None, description="Student DOB (YYYY-MM-DD or DD-MM-YYYY)"),
    current_user=Depends(require_auth),
):
    """Get all grades for a student by register number."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    # First find the student
    student = (
        supabase.table("students")
        .select("id, reg_no, name, email, dob")
        .eq("reg_no", reg_no)
        .single()
        .execute()
    )
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    _ensure_student_access(current_user, reg_no)

    if dob:
        entered_dob = _normalize_dob(dob)
        if not entered_dob:
            raise HTTPException(status_code=422, detail="DOB must be in YYYY-MM-DD or DD-MM-YYYY format")

        stored_dob = _normalize_dob(student.data.get("dob"))
        if not stored_dob:
            raise HTTPException(status_code=422, detail="DOB is not configured for this student")

        if entered_dob != stored_dob:
            raise HTTPException(status_code=401, detail="DOB verification failed")

    # Then get all their grades
    grades = (
        supabase.table("grades")
        .select("*, assessments(subject, title)")
        .eq("student_id", student.data["id"])
        .order("graded_at", desc=True)
        .execute()
    )
    return {
        "student": student.data,
        "grades": grades.data or [],
    }


@app.get("/api/students/{reg_no}/notifications")
async def get_student_notifications(
    reg_no: str,
    since: Optional[str] = Query(None, description="ISO timestamp for unread calculation"),
    current_user=Depends(require_auth),
):
    """
    In-app notification feed for student appeal outcomes.
    Returns notifications for grades that had an appeal and were later reviewed.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    student = (
        supabase.table("students")
        .select("id, reg_no, name")
        .eq("reg_no", reg_no)
        .single()
        .execute()
    )
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

    _ensure_student_access(current_user, reg_no)

    grades = (
        supabase.table("grades")
        .select("id, ai_score, prof_status, reviewed_at, appeal_reason, audit_notes, audit_feedback, assessments(subject, title)")
        .eq("student_id", student.data["id"])
        .not_.is_("appeal_reason", "null")
        .not_.is_("reviewed_at", "null")
        .in_("prof_status", ["Approved", "Overridden", "Audited"])
        .order("reviewed_at", desc=True)
        .execute()
    )

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            since_dt = None

    notifications = []
    unread_count = 0

    for row in (grades.data or []):
        assessment = row.get("assessments") or {}
        audit_notes_raw = row.get("audit_notes")
        teacher_note = "Your appeal was reviewed. Tap to view full details."
        if audit_notes_raw:
            try:
                parsed = json.loads(audit_notes_raw) if isinstance(audit_notes_raw, str) else audit_notes_raw
                teacher_note = parsed.get("recommendation") or teacher_note
            except Exception:
                pass
        elif row.get("audit_feedback"):
            feedback = row.get("audit_feedback") or []
            if isinstance(feedback, list) and feedback:
                teacher_note = str(feedback[0])

        reviewed_at = row.get("reviewed_at")
        is_unread = False
        if since_dt and reviewed_at:
            try:
                reviewed_dt = datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
                is_unread = reviewed_dt > since_dt
            except Exception:
                is_unread = False

        if is_unread:
            unread_count += 1

        notifications.append({
            "id": f"appeal-{row.get('id')}",
            "grade_id": row.get("id"),
            "type": "APPEAL_RESOLVED",
            "title": f"Appeal reviewed: {assessment.get('subject', 'Assessment')}",
            "message": f"Updated score: {row.get('ai_score')} · Status: {row.get('prof_status')}",
            "teacher_note": teacher_note,
            "status": row.get("prof_status"),
            "updated_score": row.get("ai_score"),
            "assessment_title": assessment.get("title"),
            "reviewed_at": reviewed_at,
            "is_unread": is_unread,
        })

    return {
        "student": student.data,
        "unread_count": unread_count,
        "notifications": notifications,
    }


@app.get("/api/students/{reg_no}")
async def get_student(reg_no: str, current_user=Depends(require_auth)):
    """Get a student by register number, including their grades."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    student = (
        supabase.table("students")
        .select("*, grades(*, assessments(subject, title))")
        .eq("reg_no", reg_no)
        .single()
        .execute()
    )
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")
    _ensure_student_access(current_user, reg_no)
    return student.data


# ─── Student Roster Management (COE Master List) ─────────────

class StudentCreate(BaseModel):
    reg_no: str
    name: str
    email: Opt[str] = None
    course: Opt[str] = "Data Science"


class StudentBulkCreate(BaseModel):
    students: list[StudentCreate]


@app.post("/api/students")
async def create_student(body: StudentCreate, user=Depends(require_role("ADMIN_COE", "EVALUATOR"))):
    """Add a single student to the master roster."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        result = supabase.table("students").insert({
            "reg_no": body.reg_no,
            "name": body.name,
            "email": body.email,
            "course": body.course,
        }).execute()
        return result.data[0] if result.data else result.data
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to add student: {exc}")


@app.post("/api/students/bulk")
async def bulk_create_students(body: StudentBulkCreate, user=Depends(require_role("ADMIN_COE", "EVALUATOR"))):
    """Upload a master roster (batch insert)."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    rows = [{"reg_no": s.reg_no, "name": s.name, "email": s.email, "course": s.course} for s in body.students]
    try:
        result = supabase.table("students").upsert(rows, on_conflict="reg_no").execute()
        return {"inserted": len(result.data), "students": result.data}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Bulk insert failed: {exc}")


@app.delete("/api/students/{reg_no}")
async def delete_student(reg_no: str, user=Depends(require_role("ADMIN_COE", "EVALUATOR"))):
    """Remove a student from the roster."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = supabase.table("students").delete().eq("reg_no", reg_no).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"deleted": True, "reg_no": reg_no}


# ─── Exception Handling Dashboard (Ghost Students) ───────────

@app.get("/api/exceptions")
async def list_exceptions(
    status: Opt[str] = Query("PENDING", description="Filter: PENDING, RESOLVED, REJECTED"),
    user=Depends(require_role("ADMIN_COE", "EVALUATOR", "HOD_AUDITOR")),
):
    """List all scripts routed to the exception queue."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    query = supabase.table("exception_queue").select("*, assessments(subject, title)")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).execute()
    return result.data


class ResolveExceptionBody(BaseModel):
    action: str              # "RESOLVE" or "REJECT"
    correct_reg_no: Opt[str] = None    # If resolving: the actual student reg_no to link to
    note: Opt[str] = None


@app.patch("/api/exceptions/{exception_id}")
async def resolve_exception(
    exception_id: str,
    body: ResolveExceptionBody,
    user=Depends(require_role("ADMIN_COE", "EVALUATOR", "HOD_AUDITOR")),
):
    """Resolve or reject a ghost-student exception.
    If resolving with a correct_reg_no, the grade is saved to that student."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Fetch the exception record
    exc_row = (
        supabase.table("exception_queue")
        .select("*")
        .eq("id", exception_id)
        .single()
        .execute()
    )
    if not exc_row.data:
        raise HTTPException(status_code=404, detail="Exception not found")

    exc_data = exc_row.data
    new_status = "RESOLVED" if body.action == "RESOLVE" else "REJECTED"

    # If resolving: try to save the grade to the correct student
    if body.action == "RESOLVE" and body.correct_reg_no and exc_data.get("assessment_id"):
        grade_result = save_grade_to_db(
            body.correct_reg_no,
            exc_data["assessment_id"],
            {
                "score": exc_data.get("ai_score", 0),
                "confidence": exc_data.get("confidence", 0),
                "feedback": exc_data.get("feedback", []),
                "is_flagged": True,  # Mark as flagged since it came through exception queue
            },
        )
        if not grade_result:
            raise HTTPException(
                status_code=400,
                detail=f"Corrected reg_no '{body.correct_reg_no}' also not found in roster",
            )

    # Update the exception record
    supabase.table("exception_queue").update({
        "status": new_status,
        "resolved_by": user.get("sub", "unknown") if isinstance(user, dict) else "unknown",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolution_note": body.note,
    }).eq("id", exception_id).execute()

    return {"status": new_status, "exception_id": exception_id}


# ─── Assessments endpoints ───────────────────────────────────

@app.get("/api/assessments")
async def list_assessments(current_user=Depends(require_auth)):
    """List all assessments."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = supabase.table("assessments").select("*").order("created_at", desc=True).execute()
    return result.data


# ─── Grades endpoints ────────────────────────────────────────

@app.get("/api/grades")
async def list_grades(
    status: Optional[str] = Query(None, description="Filter by prof_status"),
    current_user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")),
):
    """List all grades, optionally filtered by status."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    query = supabase.table("grades").select("*, students(reg_no, name), assessments(subject, title)")
    if status:
        query = query.eq("prof_status", status)
    result = query.order("graded_at", desc=True).execute()
    return result.data


@app.get("/api/grades/{grade_id}")
async def get_grade(grade_id: str, current_user=Depends(require_auth)):
    """Get a single grade by ID with full student + assessment details."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = (
        supabase.table("grades")
        .select("*, students(reg_no, name, email), assessments(subject, title, rubric_json)")
        .eq("id", grade_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Grade not found")
    _ensure_grade_access(current_user, result.data)
    return result.data


@app.put("/api/grades/{grade_id}/approve")
async def approve_grade(grade_id: str, user=Depends(require_role("EVALUATOR", "ADMIN_COE", "HOD_AUDITOR"))):
    """Professor approves a grade."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = (
        supabase.table("grades")
        .update({"prof_status": "Approved", "reviewed_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", grade_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Grade not found")
    _log_audit(
        grade_id=grade_id,
        action="APPROVE",
        reason="Professor approved AI grade",
        old_score=result.data[0].get("ai_score"),
        new_score=result.data[0].get("ai_score"),
        changed_by=user.get("email") or user.get("id") or "professor",
    )
    return {"message": "Grade approved", "data": result.data[0]}


@app.put("/api/grades/{grade_id}/override")
async def override_grade(grade_id: str, new_score: float = Query(...), user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR"))):
    """Professor overrides an AI grade with a manual score."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    # Fetch current score for audit trail
    current = supabase.table("grades").select("ai_score").eq("id", grade_id).single().execute()
    old_score = current.data.get("ai_score") if current.data else None
    result = (
        supabase.table("grades")
        .update({
            "prof_status": "Overridden",
            "ai_score": new_score,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", grade_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Grade not found")
    _log_audit(
        grade_id=grade_id,
        action="OVERRIDE",
        reason=f"Professor overrode AI score {old_score} → {new_score}",
        old_score=old_score,
        new_score=new_score,
        changed_by="professor",
    )
    return {"message": "Grade overridden", "data": result.data[0]}


# ─── Appeal System ────────────────────────────────────────────

@app.put("/api/grades/{grade_id}/appeal")
async def appeal_grade(
    grade_id: str,
    reason: str = Query(..., description="Reason for appeal"),
    current_user=Depends(require_auth),
):
    """Student appeals a grade — flags it for professor review."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    current_grade = (
        supabase.table("grades")
        .select("*, students(reg_no, email)")
        .eq("id", grade_id)
        .single()
        .execute()
    )
    if not current_grade.data:
        raise HTTPException(status_code=404, detail="Grade not found")
    _ensure_grade_access(current_user, current_grade.data)

    result = (
        supabase.table("grades")
        .update({
            "prof_status": "Flagged",
            "appeal_reason": reason,
        })
        .eq("id", grade_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Grade not found")
    _log_audit(
        grade_id=grade_id,
        action="APPEAL_SUBMIT",
        reason=reason,
        old_score=result.data[0].get("ai_score"),
        new_score=result.data[0].get("ai_score"),
        changed_by=current_user.get("email") or current_user.get("id") or "student",
    )
    return {"message": "Appeal submitted — professor will be notified", "data": result.data[0]}


class StaffAppealResolveBody(BaseModel):
    new_score: float
    professor_notes: str


@app.get("/api/staff/appeals/pending")
async def list_pending_appeals(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR")),
):
    """Sprint RBAC staff queue: only grades with pending student appeals."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    result = (
        supabase.table("grades")
        .select("id, ai_score, confidence, feedback, appeal_reason, prof_status, graded_at, students(reg_no, name), assessments(id, subject, title)")
        .eq("prof_status", "Flagged")
        .not_.is_("appeal_reason", "null")
        .order("graded_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@app.put("/api/staff/appeals/{grade_id}/resolve")
async def resolve_pending_appeal(
    grade_id: str,
    body: StaffAppealResolveBody,
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR")),
):
    """
    Staff Resolution Engine: override appealed score and reseal with a new SHA-256 hash.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    current = (
        supabase.table("grades")
        .select("id, ai_score, assessment_id, appeal_reason, students(reg_no, name), assessments(subject, title)")
        .eq("id", grade_id)
        .single()
        .execute()
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Grade not found")

    row = current.data
    old_score = row.get("ai_score")
    now_iso = datetime.now(timezone.utc).isoformat()
    resolver_identity = current_user.get("email") or current_user.get("id") or "staff"

    audit_notes_payload = {
        "verdict": (
            "Adjusted Up"
            if body.new_score > (old_score or 0)
            else "Adjusted Down"
            if body.new_score < (old_score or 0)
            else "Upheld"
        ),
        "recommendation": body.professor_notes,
        "rubric_breakdown": {},
        "original_score": old_score,
        "appeal_resolution": True,
        "resolved_by": resolver_identity,
        "resolved_at": now_iso,
    }

    updated = (
        supabase.table("grades")
        .update({
            "ai_score": body.new_score,
            "prof_status": "Overridden",
            "reviewed_at": now_iso,
            "audit_feedback": [body.professor_notes],
            "audit_notes": json.dumps(audit_notes_payload),
        })
        .eq("id", grade_id)
        .execute()
    )
    if not updated.data:
        raise HTTPException(status_code=500, detail="Failed to resolve appeal")

    reseal_payload = {
        "grade_id": grade_id,
        "assessment_id": row.get("assessment_id"),
        "old_score": old_score,
        "new_score": body.new_score,
        "professor_notes": body.professor_notes,
        "resolved_by": resolver_identity,
        "resolved_at": now_iso,
        "appeal_reason": row.get("appeal_reason"),
    }
    reseal_hash = hashlib.sha256(json.dumps(reseal_payload, sort_keys=True).encode("utf-8")).hexdigest()

    ledger_error = None
    try:
        supabase.table("ledger_hashes").insert({
            "assessment_id": row.get("assessment_id"),
            "filename": f"appeal-resolve-{grade_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json",
            "format": "json",
            "sha256_hash": reseal_hash,
            "record_count": 1,
            "generated_by": f"staff_resolve:{resolver_identity}",
        }).execute()
    except Exception as exc:
        ledger_error = str(exc)

    _log_audit(
        grade_id=grade_id,
        action="APPEAL_RESOLVE_OVERRIDE",
        reason=f"Staff resolved appeal: {old_score} -> {body.new_score}",
        old_score=old_score,
        new_score=body.new_score,
        changed_by=resolver_identity,
        metadata={"professor_notes": body.professor_notes, "reseal_hash": reseal_hash},
    )

    notify_appeal_resolved(
        student_reg_no=(row.get("students") or {}).get("reg_no"),
        new_score=body.new_score,
        grade_id=grade_id,
    )

    return {
        "status": "APPEAL_RESOLVED",
        "message": "Appeal resolved and score resealed.",
        "grade": updated.data[0],
        "transaction_hash": reseal_hash,
        "ledger_error": ledger_error,
    }


# ─── Audit Appeal System (The "Supreme Court") ───────────────

@app.post("/api/audit-appeal/{grade_id}")
async def run_audit_appeal(
    grade_id: str,
    current_user=Depends(require_role("HOD_AUDITOR", "ADMIN_COE")),
):
    """
    Trigger the Audit Agent for a flagged/appealed grade.
    This is the 'Head of Department' mediator that re-evaluates the grade
    using higher-reasoning and returns a binding verdict.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # 1. Fetch the grade with student + assessment details
    grade_row = (
        supabase.table("grades")
        .select("*, students(reg_no, name, email), assessments(subject, title, rubric_json, model_answer)")
        .eq("id", grade_id)
        .single()
        .execute()
    )
    if not grade_row.data:
        raise HTTPException(status_code=404, detail="Grade not found")

    grade_data = grade_row.data
    assessment_data = grade_data.get("assessments", {})
    student_data = grade_data.get("students", {})
    student_comment = grade_data.get("appeal_reason", "No reason provided.")

    # 2. Run the audit agent (synchronous — returns final result)
    try:
        audit_result = await audit_appeal_sync(
            grade_data=grade_data,
            assessment_data=assessment_data,
            student_comment=student_comment,
            student_name=student_data.get("name", "Student"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Audit agent failed: {exc}")

    # 3. Persist audit results to Supabase
    update_payload = {
        "prof_status": "Audited",
        "audit_feedback": audit_result.get("justification", []),
        "audit_score": audit_result.get("adjusted_score"),
        "audit_notes": json.dumps({
            "verdict": audit_result.get("verdict"),
            "recommendation": audit_result.get("recommendation"),
            "rubric_breakdown": audit_result.get("rubric_breakdown", {}),
            "original_score": grade_data.get("ai_score"),
        }),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }

    # If the audit adjusted the score, update ai_score too
    if audit_result.get("score_changed"):
        update_payload["ai_score"] = audit_result["adjusted_score"]
        update_payload["confidence"] = audit_result.get("adjusted_confidence", grade_data.get("confidence", 0))

    supabase.table("grades").update(update_payload).eq("id", grade_id).execute()

    _log_audit(
        grade_id=grade_id,
        action="AUDIT_ADJUST" if audit_result.get("score_changed") else "AUDIT_UPHELD",
        reason=f"Audit verdict: {audit_result.get('verdict')} — {audit_result.get('recommendation', '')[:200]}",
        old_score=grade_data.get("ai_score"),
        new_score=audit_result.get("adjusted_score"),
        changed_by="ai_audit_agent",
        metadata={"verdict": audit_result.get("verdict"), "justification_count": len(audit_result.get("justification", []))},
    )

    return {
        "status": "success",
        "grade_id": grade_id,
        "verdict": audit_result.get("verdict"),
        "original_score": grade_data.get("ai_score"),
        "adjusted_score": audit_result.get("adjusted_score"),
        "justification": audit_result.get("justification", []),
        "recommendation": audit_result.get("recommendation"),
    }


@app.post("/api/audit-appeal/{grade_id}/stream")
async def run_audit_appeal_stream(
    grade_id: str,
    current_user=Depends(require_role("HOD_AUDITOR", "ADMIN_COE")),
):
    """
    SSE streaming version of the audit agent.
    The staff dashboard can render each deliberation step in real-time.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Fetch grade + assessment + student
    grade_row = (
        supabase.table("grades")
        .select("*, students(reg_no, name, email), assessments(subject, title, rubric_json, model_answer)")
        .eq("id", grade_id)
        .single()
        .execute()
    )
    if not grade_row.data:
        raise HTTPException(status_code=404, detail="Grade not found")

    grade_data = grade_row.data
    assessment_data = grade_data.get("assessments", {})
    student_data = grade_data.get("students", {})
    student_comment = grade_data.get("appeal_reason", "No reason provided.")

    async def event_generator():
        audit_result = None

        async for event_str in audit_appeal_stream(
            grade_data=grade_data,
            assessment_data=assessment_data,
            student_comment=student_comment,
            student_name=student_data.get("name", "Student"),
        ):
            # Capture audit result for DB persistence
            if event_str.startswith("event: audit_result"):
                data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                audit_result = json.loads(data_line)

            yield event_str

        # Persist to Supabase after stream completes
        if audit_result:
            update_payload = {
                "prof_status": "Audited",
                "audit_feedback": audit_result.get("justification", []),
                "audit_score": audit_result.get("adjusted_score"),
                "audit_notes": json.dumps({
                    "verdict": audit_result.get("verdict"),
                    "recommendation": audit_result.get("recommendation"),
                    "rubric_breakdown": audit_result.get("rubric_breakdown", {}),
                    "original_score": grade_data.get("ai_score"),
                }),
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
            if audit_result.get("score_changed"):
                update_payload["ai_score"] = audit_result["adjusted_score"]
                update_payload["confidence"] = audit_result.get("adjusted_confidence", grade_data.get("confidence", 0))

            try:
                supabase.table("grades").update(update_payload).eq("id", grade_id).execute()
                yield f"event: db\ndata: {json.dumps({'saved': True, 'verdict': audit_result.get('verdict')})}\n\n"
            except Exception as exc:
                yield f"event: db\ndata: {json.dumps({'saved': False, 'reason': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── PDF Preview (convert ALL pages to one stitched JPEG) ────

@app.post("/api/pdf-preview")
async def pdf_preview(file: UploadFile = File(...), current_user=Depends(require_auth)):
    """Convert all pages of a PDF to one stitched JPEG and return as base64."""
    raw = await file.read()
    content_type = file.content_type or ""
    fname = (file.filename or "").lower()

    if not (content_type == "application/pdf" or fname.endswith(".pdf")):
        return JSONResponse({"preview": None, "reason": "Not a PDF"}, status_code=200)

    try:
        import fitz  # PyMuPDF
        import base64
        doc = fitz.open(stream=raw, filetype="pdf")
        n_pages = doc.page_count

        # Lower resolution for preview (1.2x for speed)
        mat = fitz.Matrix(1.2, 1.2)

        if n_pages == 1:
            pix = doc[0].get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
        else:
            import numpy as np
            import cv2
            strips = []
            for i in range(n_pages):
                pix = doc[i].get_pixmap(matrix=mat)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n == 4:
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                elif pix.n == 3:
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                strips.append(arr)

            max_w = max(s.shape[1] for s in strips)
            resized = []
            for s in strips:
                if s.shape[1] != max_w:
                    scale = max_w / s.shape[1]
                    s = cv2.resize(s, (max_w, int(s.shape[0] * scale)))
                resized.append(s)

            stitched = np.vstack(resized)
            _, buf = cv2.imencode(".jpg", stitched, [cv2.IMWRITE_JPEG_QUALITY, 75])
            img_bytes = buf.tobytes()

        doc.close()
        b64 = base64.b64encode(img_bytes).decode()
        return JSONResponse({"preview": f"data:image/jpeg;base64,{b64}", "pages": n_pages})
    except Exception as exc:
        return JSONResponse({"preview": None, "reason": str(exc)}, status_code=200)


# ─── Script Header Parser (Auto-ID Vision Agent) ─────────────

@app.post("/api/parse-header")
async def parse_script_header(
    file: UploadFile = File(...),
    match_db: bool = Query(True, description="Try to match reg_no against Supabase students"),
    current_user=Depends(require_auth),
):
    """
    Upload an answer-sheet image → Vision Agent extracts reg_no, subject_code
    from the header section. Optionally matches against Supabase records.
    """
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    if match_db and supabase:
        result = await identify_and_match_student(
            image_bytes=image_bytes,
            mime_type=mime_type,
            supabase_client=supabase,
        )
        return result
    else:
        header = await identify_student_from_header(image_bytes, mime_type)
        return {"header": header, "student": None, "assessment": None, "matched": False}


# ─── Institutional Audit Logs ─────────────────────────────────

def _log_audit(
    grade_id: str,
    action: str,
    reason: str,
    old_score: float = None,
    new_score: float = None,
    changed_by: str = "system",
    metadata: dict = None,
):
    """Insert a row into audit_logs. Non-blocking — failures are silently ignored."""
    if not supabase:
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
    except Exception:
        pass  # Audit logging should never break the main flow


@app.get("/api/audit-logs")
async def list_audit_logs(
    grade_id: Optional[str] = Query(None, description="Filter by grade ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, description="Max results"),
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """
    List institutional audit log entries.
    Used by the CoE Admin Dashboard for compliance review.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        query = supabase.table("audit_logs").select("*")
        if grade_id:
            query = query.eq("grade_id", grade_id)
        if action:
            query = query.eq("action", action)
        result = query.order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception:
        return []  # Table may not exist yet


@app.get("/api/audit-logs/stats")
async def audit_log_stats(current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR"))):
    """Aggregate counts by action type for the admin dashboard."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        logs = supabase.table("audit_logs").select("action").execute()
        counts: dict = {}
        for row in (logs.data or []):
            a = row.get("action", "UNKNOWN")
            counts[a] = counts.get(a, 0) + 1
        return counts
    except Exception:
        return {}  # Table may not exist yet


# ─── Admin (CoE) Dashboard Stats ─────────────────────────────

@app.get("/api/admin/stats")
async def admin_dashboard_stats(user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR"))):
    """
    Aggregate statistics for the Controller of Examinations dashboard.
    Returns total scripts, status breakdown, appeal count, avg confidence, etc.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Fetch all grades (lightweight — only needed columns)
    # Try with audit_score first; fall back if column doesn't exist yet
    try:
        grades = (
            supabase.table("grades")
            .select("ai_score, confidence, prof_status, is_flagged, appeal_reason, audit_score")
            .execute()
        )
    except Exception:
        grades = (
            supabase.table("grades")
            .select("ai_score, confidence, prof_status, is_flagged, appeal_reason")
            .execute()
        )
    all_grades = grades.data or []

    total = len(all_grades)
    if total == 0:
        return {
            "total_scripts": 0,
            "total_students": 0,
            "status_breakdown": {},
            "pending_appeals": 0,
            "flagged_count": 0,
            "avg_score": 0,
            "avg_confidence": 0,
            "audited_count": 0,
            "audit_overturn_rate": 0,
        }

    # Status breakdown
    status_counts: dict = {}
    flagged = 0
    appeals = 0
    audited = 0
    audit_changed = 0
    score_sum = 0.0
    conf_sum = 0.0

    for g in all_grades:
        st = g.get("prof_status", "Pending")
        status_counts[st] = status_counts.get(st, 0) + 1
        if g.get("is_flagged"):
            flagged += 1
        if g.get("appeal_reason"):
            appeals += 1
        if st == "Audited":
            audited += 1
            if g.get("audit_score") is not None and g.get("audit_score") != g.get("ai_score"):
                audit_changed += 1
        score_sum += g.get("ai_score", 0)
        conf_sum += g.get("confidence", 0)

    # Fetch total students for context
    students_res = supabase.table("students").select("id", count="exact").execute()
    total_students = students_res.count if hasattr(students_res, "count") and students_res.count else len(students_res.data or [])

    return {
        "total_scripts": total,
        "total_students": total_students,
        "status_breakdown": status_counts,
        "pending_appeals": status_counts.get("Flagged", 0),
        "flagged_count": flagged,
        "avg_score": round(score_sum / total, 2) if total else 0,
        "avg_confidence": round(conf_sum / total, 3) if total else 0,
        "audited_count": audited,
        "audit_overturn_rate": round(audit_changed / audited, 3) if audited else 0,
    }


@app.get("/api/admin/recent-activity")
async def admin_recent_activity(
    limit: int = Query(20),
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """
    Recent grade + audit activity for the admin control tower.
    Returns the most recent grades with student + assessment info.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    result = (
        supabase.table("grades")
        .select("id, ai_score, confidence, prof_status, is_flagged, graded_at, reviewed_at, students(reg_no, name), assessments(subject, title)")
        .order("graded_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@app.get("/api/admin/audit-records")
async def admin_audit_records(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """Enterprise audit view rows with hash verification metadata."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    grades_res = (
        supabase.table("grades")
        .select("id, assessment_id, ai_score, confidence, feedback, prof_status, graded_at, students(reg_no, name), assessments(subject, title)")
        .order("graded_at", desc=True)
        .limit(limit)
        .execute()
    )
    grades = grades_res.data or []

    assessment_ids = list({g.get("assessment_id") for g in grades if g.get("assessment_id")})
    sealed_assessments: set[str] = set()
    if assessment_ids:
        try:
            hash_rows = (
                supabase.table("ledger_hashes")
                .select("assessment_id")
                .in_("assessment_id", assessment_ids)
                .execute()
            )
            for row in (hash_rows.data or []):
                aid = row.get("assessment_id")
                if aid:
                    sealed_assessments.add(aid)
        except Exception:
            pass

    records = []
    for row in grades:
        student = row.get("students") or {}
        assessment = row.get("assessments") or {}
        assessment_id = row.get("assessment_id")
        hash_payload = {
            "grade_id": row.get("id"),
            "student_id": student.get("reg_no"),
            "assessment_id": assessment_id,
            "score": row.get("ai_score"),
            "graded_at": row.get("graded_at"),
        }
        tx_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode("utf-8")).hexdigest()
        records.append(
            {
                "grade_id": row.get("id"),
                "student_id": student.get("reg_no"),
                "student_name": student.get("name"),
                "status": row.get("prof_status"),
                "score": row.get("ai_score"),
                "confidence": row.get("confidence"),
                "feedback_trace": row.get("feedback") or [],
                "subject": assessment.get("subject"),
                "title": assessment.get("title"),
                "graded_at": row.get("graded_at"),
                "scan_image_url": None,
                "hash_verify": "VERIFIED" if assessment_id in sealed_assessments else "PENDING",
                "transaction_hash": tx_hash,
            }
        )
    return records


# ─── ERP Export Module — Ledger Generation & Download ─────────

def _fetch_finalized_grades(assessment_id: str) -> list:
    """Fetch only Approved/Audited grades for an assessment."""
    if not supabase:
        return []
    # Try with both Approved + Audited; fall back to Approved-only
    # (Audited may not exist in older DB enum definitions)
    try:
        result = (
            supabase.table("grades")
            .select("*, students(reg_no, name), assessments(subject, title)")
            .eq("assessment_id", assessment_id)
            .in_("prof_status", ["Approved", "Audited"])
            .order("graded_at")
            .execute()
        )
        return result.data or []
    except Exception:
        try:
            result = (
                supabase.table("grades")
                .select("*, students(reg_no, name), assessments(subject, title)")
                .eq("assessment_id", assessment_id)
                .eq("prof_status", "Approved")
                .order("graded_at")
                .execute()
            )
            return result.data or []
        except Exception:
            return []


@app.get("/api/ledger/{assessment_id}/preview")
async def preview_ledger(
    assessment_id: str,
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR")),
):
    """
    JSON preview of the marks ledger for an assessment.
    Shows what will be exported before the CoE clicks "Finalize".
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    grades = _fetch_finalized_grades(assessment_id)
    preview = generate_ledger_preview(grades, limit=20)

    # Also include assessment meta
    try:
        assessment = (
            supabase.table("assessments")
            .select("id, subject, title, is_locked, locked_at")
            .eq("id", assessment_id)
            .single()
            .execute()
        )
        preview["assessment"] = assessment.data
    except Exception:
        preview["assessment"] = None

    return preview


@app.get("/api/ledger/{assessment_id}/download")
async def download_ledger(
    assessment_id: str,
    fmt: str = Query("csv", description="Export format: csv or xlsx"),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """
    Generate and download the marks ledger as CSV or Excel.
    Also persists the SHA-256 hash to the ledger_hashes table.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    grades = _fetch_finalized_grades(assessment_id)
    if not grades:
        raise HTTPException(
            status_code=404,
            detail="No approved/audited grades found for this assessment.",
        )

    ledger = generate_university_ledger(grades, assessment_id, fmt=fmt)
    if not ledger.get("filename"):
        raise HTTPException(status_code=500, detail=ledger.get("error", "Export failed"))

    # Persist the hash to Supabase
    try:
        supabase.table("ledger_hashes").insert({
            "assessment_id": assessment_id,
            "filename": ledger["filename"],
            "format": ledger["format"],
            "sha256_hash": ledger["sha256"],
            "record_count": ledger["records"],
            "generated_by": "coe_admin",
        }).execute()
    except Exception:
        pass  # Hash storage is non-critical; download still works

    _log_audit(
        grade_id=None,
        action="LEDGER_EXPORT",
        reason=f"Marks ledger exported: {ledger['filename']} ({ledger['records']} records, {fmt})",
        changed_by="coe_admin",
        metadata={"sha256": ledger["sha256"], "records": ledger["records"], "format": fmt},
    )

    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "text/csv"
    return StreamingResponse(
        io.BytesIO(ledger["content"]),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{ledger["filename"]}"'},
    )


@app.get("/api/ledger/{assessment_id}/hashes")
async def list_ledger_hashes(
    assessment_id: str,
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """List all previously generated ledger hashes for an assessment."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        result = (
            supabase.table("ledger_hashes")
            .select("*")
            .eq("assessment_id", assessment_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


@app.post("/api/ledger/{assessment_id}/verify")
async def verify_ledger_integrity(
    assessment_id: str,
    file: UploadFile = File(...),
    current_user=Depends(require_auth),
):
    """
    Verify a previously exported ledger file against stored hashes.
    Upload the file → compute SHA-256 → compare against ledger_hashes table.
    Returns whether the file is AUTHENTIC or TAMPERED.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    content = await file.read()
    computed_hash = generate_integrity_hash(content)

    # Check against stored hashes
    try:
        result = (
            supabase.table("ledger_hashes")
            .select("id, filename, sha256_hash, created_at")
            .eq("assessment_id", assessment_id)
            .eq("sha256_hash", computed_hash)
            .execute()
        )
        if result.data:
            match = result.data[0]
            return {
                "status": "AUTHENTIC",
                "message": "Digital seal verified — file has NOT been tampered with.",
                "matched_hash_id": match["id"],
                "original_filename": match["filename"],
                "generated_at": match["created_at"],
                "computed_hash": computed_hash,
            }
        else:
            return {
                "status": "TAMPERED",
                "message": "WARNING: File hash does NOT match any known ledger. It may have been modified.",
                "computed_hash": computed_hash,
            }
    except Exception:
        return {
            "status": "ERROR",
            "message": "Could not verify — ledger_hashes table may not exist yet.",
            "computed_hash": computed_hash,
        }


# ─── Finalize & Lock Assessment ───────────────────────────────

@app.post("/api/assessments/{assessment_id}/lock")
async def finalize_and_lock(
    assessment_id: str,
    fmt: str = Query("csv", description="Ledger format: csv or xlsx"),
    user=Depends(require_role("ADMIN_COE")),
):
    """
    THE FINAL STEP — CoE clicks "Finalize & Lock".

    1. Generates the official marks ledger (CSV/XLSX)
    2. Computes SHA-256 integrity hash (digital seal)
    3. Stores the hash in ledger_hashes
    4. Sets is_locked=true on the assessment
    5. Logs the action to audit_logs

    After this, grades for this assessment cannot be edited.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Check if already locked
    try:
        assessment = (
            supabase.table("assessments")
            .select("id, subject, title, is_locked")
            .eq("id", assessment_id)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Assessment not found")

    if not assessment.data:
        raise HTTPException(status_code=404, detail="Assessment not found")

    if assessment.data.get("is_locked"):
        raise HTTPException(
            status_code=409,
            detail="Assessment is already locked. Marks cannot be modified.",
        )

    # 1. Fetch finalized grades
    grades = _fetch_finalized_grades(assessment_id)
    if not grades:
        raise HTTPException(
            status_code=400,
            detail="No approved/audited grades found. Approve grades before locking.",
        )

    # 2. Generate ledger + hash
    ledger = generate_university_ledger(grades, assessment_id, fmt=fmt)
    if not ledger.get("filename"):
        raise HTTPException(status_code=500, detail="Ledger generation failed")

    # 3. Store hash
    try:
        supabase.table("ledger_hashes").insert({
            "assessment_id": assessment_id,
            "filename": ledger["filename"],
            "format": ledger["format"],
            "sha256_hash": ledger["sha256"],
            "record_count": ledger["records"],
            "generated_by": "coe_admin_finalize",
        }).execute()
    except Exception:
        pass

    # 4. Lock the assessment
    supabase.table("assessments").update({
        "is_locked": True,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "locked_by": "coe_admin",
    }).eq("id", assessment_id).execute()

    # 5. Audit log
    _log_audit(
        grade_id=None,
        action="FINALIZE_LOCK",
        reason=f"Assessment locked by CoE — {ledger['records']} records, SHA-256: {ledger['sha256'][:16]}…",
        changed_by="coe_admin",
        metadata={
            "assessment_id": assessment_id,
            "sha256": ledger["sha256"],
            "filename": ledger["filename"],
            "records": ledger["records"],
            "format": fmt,
        },
    )

    return {
        "status": "locked",
        "assessment_id": assessment_id,
        "subject": assessment.data.get("subject"),
        "title": assessment.data.get("title"),
        "ledger_filename": ledger["filename"],
        "sha256_hash": ledger["sha256"],
        "records_exported": ledger["records"],
        "format": fmt,
        "message": "Assessment marks are now LOCKED. Ledger generated and digitally signed.",
    }


@app.get("/api/assessments/{assessment_id}/lock-status")
async def get_lock_status(
    assessment_id: str,
    current_user=Depends(require_auth),
):
    """Check if an assessment is locked and return lock metadata."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        # Try with lock columns first; fall back to basic select
        try:
            result = (
                supabase.table("assessments")
                .select("id, subject, title, is_locked, locked_at, locked_by")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
        except Exception:
            result = (
                supabase.table("assessments")
                .select("id, subject, title")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
            if result.data:
                result.data["is_locked"] = False
                result.data["locked_at"] = None
                result.data["locked_by"] = None

        if not result.data:
            raise HTTPException(status_code=404, detail="Assessment not found")

        # Get latest ledger hash
        hashes = []
        try:
            h = (
                supabase.table("ledger_hashes")
                .select("filename, sha256_hash, record_count, format, created_at")
                .eq("assessment_id", assessment_id)
                .order("created_at", desc=True)
                .limit(3)
                .execute()
            )
            hashes = h.data or []
        except Exception:
            pass

        return {
            **result.data,
            "ledger_hashes": hashes,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Assessment not found")


# ─── Semantic Gap Analysis (Knowledge Mapping) ───────────────

@app.get("/api/knowledge-map/{assessment_id}")
async def get_knowledge_map(
    assessment_id: str,
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """
    Retrieves the Class Semantic Gap Analysis for the CoE.
    Protected: only ADMIN_COE or HOD_AUDITOR can access institutional intelligence.
    Returns formatted data for the Recharts Radar Chart + remediation plan.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        result = await generate_formatted_knowledge_map(assessment_id, supabase)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Knowledge map generation failed: {exc}")


@app.get("/api/knowledge-map/compare")
async def compare_knowledge_maps(
    assessment_1: str = Query(..., description="First assessment UUID"),
    assessment_2: str = Query(..., description="Second assessment UUID"),
    current_user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR")),
):
    """
    Compare knowledge maps between two assessments to track
    pedagogical improvement or regression across the semester.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        result = await compare_assessments(assessment_1, assessment_2, supabase)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {exc}")


# ─── Diagram-to-Code Validation ──────────────────────────────

@app.post("/api/diagram/detect")
async def detect_diagram_in_image(
    file: UploadFile = File(...),
    current_user=Depends(require_auth),
):
    """
    Detect whether an uploaded answer sheet contains diagrams.
    Returns diagram types, locations, and classification.
    """
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    try:
        result = await detect_diagrams(image_bytes, mime_type)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Diagram detection failed: {exc}")


@app.post("/api/diagram/validate")
async def validate_diagram(
    file: UploadFile = File(...),
    current_user=Depends(require_auth),
):
    """
    Convert a handwritten diagram to Mermaid.js code and validate
    its structural and logical correctness.
    Returns mermaid_code, validity assessment, and logic flaws.
    """
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    try:
        result = await validate_diagram_logic(image_bytes, mime_type)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Diagram validation failed: {exc}")


@app.post("/api/diagram/validate/stream")
async def validate_diagram_streaming(
    file: UploadFile = File(...),
    current_user=Depends(require_auth),
):
    """
    SSE streaming version of diagram validation.
    Shows each step of the detection → conversion → validation pipeline.
    """
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"

    return StreamingResponse(
        diagram_validation_stream(image_bytes, mime_type),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Similarity Sentinel — Collusion Detection ──────────────

@app.post("/api/sentinel/check/{grade_id}")
async def sentinel_check_grade(
    grade_id: str,
    threshold: float = Query(0.92, description="Similarity threshold (0-1)"),
    current_user=Depends(require_auth),
):
    """
    Check a specific grade for collusion against other submissions
    in the same assessment.  Also indexes the submission into Pinecone.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Fetch the grade + student info
    grade = (
        supabase.table("grades")
        .select("*, students(reg_no, name), assessments(subject, title)")
        .eq("id", grade_id)
        .single()
        .execute()
    )
    if not grade.data:
        raise HTTPException(status_code=404, detail="Grade not found")

    g = grade.data
    feedback = g.get("feedback", [])
    answer_text = " ".join(str(f) for f in feedback) if isinstance(feedback, list) else str(feedback)

    if len(answer_text) < 20:
        return {"is_flagged": False, "potential_collusion_with": [], "message": "Submission too short to analyse"}

    student_info = g.get("students", {})
    reg_no = student_info.get("reg_no", "—") if isinstance(student_info, dict) else "—"

    # Index this submission for future comparisons
    await index_student_submission(
        grade_id=grade_id,
        student_id=g["student_id"],
        assessment_id=g["assessment_id"],
        reg_no=reg_no,
        answer_text=answer_text,
        graded_at=g.get("graded_at"),
    )

    # Check against existing submissions
    report = await check_collusion_risk(
        current_student_id=g["student_id"],
        answer_text=answer_text,
        assessment_id=g["assessment_id"],
        threshold=threshold,
    )

    # Log if flagged
    if report.get("is_flagged"):
        _log_audit(
            grade_id=grade_id,
            action="COLLUSION_FLAG",
            reason=f"Similarity sentinel flagged {len(report['potential_collusion_with'])} match(es)",
            old_score=g.get("ai_score"),
            new_score=g.get("ai_score"),
            changed_by="sentinel",
            metadata={"matches": report["potential_collusion_with"]},
        )

    return report


@app.get("/api/sentinel/scan/{assessment_id}")
async def sentinel_scan_assessment(
    assessment_id: str,
    threshold: float = Query(0.90, description="Similarity threshold (0-1)"),
    current_user=Depends(require_auth),
):
    """
    Batch-scan all submissions for an assessment to detect collusion.
    Returns a list of flagged pairs sorted by similarity.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    report = await scan_assessment_collusion(
        assessment_id=assessment_id,
        supabase_client=supabase,
        threshold=threshold,
    )
    return report


@app.get("/api/sentinel/flags")
async def sentinel_all_flags(
    threshold: float = Query(0.90, description="Similarity threshold (0-1)"),
    limit: int = Query(20, description="Max flag pairs to return"),
    current_user=Depends(require_auth),
):
    """
    Retrieve collusion flags across ALL assessments.
    Aggregates scan results for the CoE dashboard.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Get all assessments
    assessments = supabase.table("assessments").select("id, subject, title").execute()
    all_flags = []

    for a in (assessments.data or []):
        report = await scan_assessment_collusion(
            assessment_id=a["id"],
            supabase_client=supabase,
            threshold=threshold,
        )
        for flag in report.get("flags", []):
            flag["assessment_subject"] = a.get("subject", "")
            flag["assessment_title"] = a.get("title", "")
            all_flags.append(flag)

    # Sort globally by similarity
    all_flags.sort(key=lambda f: f["similarity"], reverse=True)

    return {
        "flags": all_flags[:limit],
        "total_flags": len(all_flags),
    }


# ─── Institutional Ledger Export (Marks + Sentinel + Digital Seal) ────

@app.get("/api/institutional-ledger/{assessment_id}/download")
async def download_institutional_ledger(
    assessment_id: str,
    fmt: str = Query("csv", description="Export format: csv or xlsx"),
    sentinel_threshold: float = Query(0.90, description="Sentinel similarity threshold (0-1)"),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """
    Generate the comprehensive Institutional Ledger export.

    Combines:
    1. Student marks (from grades table)
    2. Similarity Sentinel flags (real-time Pinecone scan)
    3. SHA-256 digital seal (tamper-proof hash)

    This is the final document sent to the university ERP system.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    # 1. Fetch approved grades
    grades = _fetch_finalized_grades(assessment_id)
    if not grades:
        raise HTTPException(
            status_code=404,
            detail="No approved/audited grades found for this assessment.",
        )

    # 2. Run sentinel scan to get collusion flags
    sentinel_report = await scan_assessment_collusion(
        assessment_id=assessment_id,
        supabase_client=supabase,
        threshold=sentinel_threshold,
    )

    # Build student_id → sentinel info lookup
    sentinel_flags: dict[str, dict] = {}
    for flag in sentinel_report.get("flags", []):
        for side in [("studentA_id", "studentA", "studentB"), ("studentB_id", "studentB", "studentA")]:
            sid, self_key, peer_key = side
            student_id = flag.get(sid, "")
            if student_id and student_id not in sentinel_flags:
                sentinel_flags[student_id] = {
                    "status": flag.get("status", "Warning"),
                    "similarity": flag.get("similarity", 0),
                    "peer": flag.get(peer_key, "—"),
                }

    # 3. Generate the institutional ledger with all three layers
    ledger = generate_institutional_ledger(
        grades_data=grades,
        assessment_id=assessment_id,
        sentinel_flags=sentinel_flags,
        fmt=fmt,
    )

    if not ledger.get("filename"):
        raise HTTPException(status_code=500, detail=ledger.get("error", "Export failed"))

    # 4. Persist hash
    try:
        supabase.table("ledger_hashes").insert({
            "assessment_id": assessment_id,
            "filename": ledger["filename"],
            "format": ledger["format"],
            "sha256_hash": ledger["sha256"],
            "record_count": ledger["records"],
            "generated_by": "institutional_export",
        }).execute()
    except Exception:
        pass

    # 5. Audit log
    _log_audit(
        grade_id=None,
        action="INSTITUTIONAL_EXPORT",
        reason=(
            f"Institutional ledger exported: {ledger['filename']} "
            f"({ledger['records']} records, {fmt}, "
            f"{len(sentinel_flags)} sentinel flags)"
        ),
        changed_by="coe_admin",
        metadata={
            "sha256": ledger["sha256"],
            "records": ledger["records"],
            "format": fmt,
            "sentinel_flags_count": len(sentinel_flags),
            "sentinel_threshold": sentinel_threshold,
        },
    )

    mime = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if fmt == "xlsx"
        else "text/csv"
    )
    return StreamingResponse(
        io.BytesIO(ledger["content"]),
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{ledger["filename"]}"',
            "X-SHA256-Seal": ledger["sha256"],
            "X-Sentinel-Flags": str(len(sentinel_flags)),
        },
    )


@app.get("/api/institutional-ledger/{assessment_id}/preview")
async def preview_institutional_ledger(
    assessment_id: str,
    sentinel_threshold: float = Query(0.90),
    current_user=Depends(require_role("ADMIN_COE")),
):
    """
    JSON preview of the institutional ledger including sentinel flags.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

    grades = _fetch_finalized_grades(assessment_id)

    # Sentinel scan
    sentinel_report = await scan_assessment_collusion(
        assessment_id=assessment_id,
        supabase_client=supabase,
        threshold=sentinel_threshold,
    )

    sentinel_flags: dict[str, dict] = {}
    for flag in sentinel_report.get("flags", []):
        for side in [("studentA_id", "studentA", "studentB"), ("studentB_id", "studentB", "studentA")]:
            sid, self_key, peer_key = side
            student_id = flag.get(sid, "")
            if student_id and student_id not in sentinel_flags:
                sentinel_flags[student_id] = {
                    "status": flag.get("status", "Warning"),
                    "similarity": flag.get("similarity", 0),
                    "peer": flag.get(peer_key, "\u2014"),
                }

    # Assessment meta
    assessment_meta = None
    try:
        a = (
            supabase.table("assessments")
            .select("id, subject, title, is_locked, locked_at")
            .eq("id", assessment_id)
            .single()
            .execute()
        )
        assessment_meta = a.data
    except Exception:
        pass

    # Build preview rows
    preview_rows = []
    for entry in grades[:20]:  # limit preview
        student = entry.get("students") or {}
        student_id = entry.get("student_id", "")
        sentinel = sentinel_flags.get(student_id, {})
        preview_rows.append({
            "reg_no": student.get("reg_no", "N/A"),
            "name": student.get("name", "N/A"),
            "marks": round(entry.get("ai_score", 0), 2),
            "confidence": round(entry.get("confidence", 0) * 100, 1),
            "status": entry.get("prof_status", "Pending"),
            "sentinel_status": sentinel.get("status", "Clear"),
            "sentinel_similarity": sentinel.get("similarity", ""),
            "sentinel_peer": sentinel.get("peer", ""),
        })

    return {
        "assessment": assessment_meta,
        "total_records": len(grades),
        "sentinel_flags_count": len(sentinel_flags),
        "preview": preview_rows,
    }


# ---------------------------------------------------------
# DEMO DATABASE (For the presentation)
# In production, this is your Supabase / PostgreSQL database.
# This in-memory dict lets the demo flow work seamlessly:
#   POST /api/evaluate  →  grades the paper  →  saves to db
#   GET  /api/results/AD011  →  returns that grade instantly
# ---------------------------------------------------------
from collections import OrderedDict

class MockDatabase:
    """Bounded in-memory results store keyed by registration number.
    Evicts the oldest entry when MAX_ENTRIES is reached to prevent
    unbounded memory growth during long demo sessions."""
    MAX_ENTRIES = 500

    def __init__(self):
        self.results_table: OrderedDict = OrderedDict()

    def save(self, reg_no: str, data: dict):
        if reg_no in self.results_table:
            self.results_table.move_to_end(reg_no)
        self.results_table[reg_no] = data
        while len(self.results_table) > self.MAX_ENTRIES:
            self.results_table.popitem(last=False)

db = MockDatabase()


@app.get("/api/results/{reg_no}")
async def get_student_results(reg_no: str, current_user=Depends(require_auth)):
    """
    The endpoint your React Native mobile app will call.
    Example: GET http://127.0.0.1:8000/api/results/AD011

    Separation of Concerns:
      - POST /api/evaluate  → heavy AI processing (SSE stream)
      - GET  /api/results   → lightning-fast lookup, perfect for
        a mobile app on spotty college Wi-Fi
    """
    print(f"📱 Mobile App requested results for: {reg_no}")

    # Normalise to uppercase so "ad011" matches "AD011"
    search_reg_no = reg_no.upper()
    _ensure_student_access(current_user, search_reg_no)

    if search_reg_no not in db.results_table:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No IA-1 results found for Registration Number: {search_reg_no}. "
                "Your paper may still be under review."
            ),
        )

    student_data = db.results_table[search_reg_no]

    return {
        "status": "success",
        "message": "Results retrieved successfully.",
        "data": student_data,
    }


# ---------------------------------------------------------
# BATCH PROCESSING ENGINE
# Enterprise-grade async pipeline for multi-image & PDF grading.
#
# Architecture:
#   POST /api/evaluate-batch  →  accepts List[UploadFile]
#                              →  returns job_id immediately
#                              →  processes all pages in background
#   GET  /api/batch-status/{job_id}  →  polling endpoint for progress
#
# PDF Handling:
#   PyMuPDF renders each page into a 300-DPI image, which is then
#   fed into the same agentic_grade_stream pipeline as a regular
#   photo upload. A final aggregation step merges cross-page answers.
# ---------------------------------------------------------

# In-memory job store (production: use Redis or Supabase)
_batch_jobs: dict = {}

MAX_BATCH_FILES = 20
MAX_BATCH_FILE_SIZE = 15 * 1024 * 1024  # 15 MB per file


class BatchJob:
    """Tracks the lifecycle of a batch grading job."""
    def __init__(self, job_id: str, total_pages: int, detected_student: dict | None = None):
        self.job_id = job_id
        self.status = "processing"  # processing | completed | failed
        self.total_pages = total_pages
        self.processed_pages = 0
        self.results: list[dict] = []
        self.errors: list[str] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None
        self.aggregated_result: dict | None = None
        self.detected_student = detected_student  # Auto-ID from header parser


def _pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> list[tuple[bytes, str]]:
    """Convert every page of a PDF into high-res JPEG images.

    Returns a list of (image_bytes, mime_type) tuples.
    Uses PyMuPDF's get_pixmap() at the specified DPI for
    crystal-clear handwriting recognition.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.is_encrypted:
        doc.close()
        raise ValueError("Encrypted PDFs are not supported.")

    images = []
    zoom = dpi / 72  # fitz default is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Convert to JPEG bytes
        img_bytes = pix.tobytes("jpeg")
        images.append((img_bytes, "image/jpeg"))
        print(f"  📄 PDF page {page_num + 1}/{len(doc)} → {len(img_bytes) // 1024}KB image")

    doc.close()
    return images


async def _process_batch_job(job_id: str, pages: list[tuple[bytes, str]], rubric_text: str | None, detected_reg_no: str | None = None, detected_assessment_id: str | None = None):
    """Background worker that grades each page through the full pipeline."""
    job = _batch_jobs.get(job_id)
    if not job:
        return

    try:
        for i, (image_bytes, mime_type) in enumerate(pages):
            page_label = f"Page {i + 1}/{job.total_pages}"
            print(f"🔄 [{job_id}] Grading {page_label}...")

            try:
                # Collect the full SSE stream for this page into a result dict
                page_result: dict | None = None
                async for event_str in agentic_grade_stream(
                    image_bytes,
                    mime_type=mime_type,
                    dynamic_rubric_text=rubric_text,
                ):
                    # Capture the final result event
                    if event_str.startswith("event: result"):
                        try:
                            data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                            page_result = json.loads(data_line)
                        except Exception:
                            pass

                if page_result:
                    page_result["_page_number"] = i + 1
                    job.results.append(page_result)
                    print(f"✅ [{job_id}] {page_label} graded — score: {page_result.get('score', '?')}")
                else:
                    job.errors.append(f"{page_label}: No result returned from grading pipeline")

            except Exception as page_err:
                job.errors.append(f"{page_label}: {str(page_err)}")
                print(f"❌ [{job_id}] {page_label} failed: {page_err}")

            job.processed_pages = i + 1

            # Rate-limit between pages to avoid Gemini 429s
            if i < len(pages) - 1:
                await asyncio.sleep(2)

        # ── Aggregate results across all pages ─────────────────
        if job.results:
            job.aggregated_result = _aggregate_batch_results(job.results)

            # Override reg_no with header-parser auto-detection if available
            if detected_reg_no and detected_reg_no != "FLAG_FOR_MANUAL":
                job.aggregated_result["registration_number"] = detected_reg_no.upper()

            # Save aggregated result to MockDatabase
            reg = (
                job.aggregated_result.get("registration_number")
                or job.aggregated_result.get("reg_no")
                or "UNKNOWN"
            ).upper()
            if reg != "UNKNOWN":
                db.save(reg, job.aggregated_result)
                print(f"💾 [{job_id}] Aggregated result saved for {reg}")

            # ── Sync to Supabase grades table ────────────────
            if reg != "UNKNOWN" and detected_assessment_id and supabase:
                try:
                    db_record = save_grade_to_db(
                        student_reg_no=reg,
                        assessment_id=detected_assessment_id,
                        ai_results=job.aggregated_result,
                    )
                    if db_record:
                        job.aggregated_result["synced_to_supabase"] = True
                        job.aggregated_result["student_name"] = (
                            (job.detected_student or {}).get("student", {}) or {}
                        ).get("name", reg)
                        print(f"🗄️ [{job_id}] Grade synced to Supabase for {reg}")
                    else:
                        job.aggregated_result["synced_to_supabase"] = False
                        print(f"⚠️ [{job_id}] Supabase sync skipped (student not in roster?)")
                except Exception as sync_err:
                    job.aggregated_result["synced_to_supabase"] = False
                    print(f"⚠️ [{job_id}] Supabase sync failed: {sync_err}")

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        print(f"🏁 [{job_id}] Batch job complete — {len(job.results)}/{job.total_pages} pages graded")

    except Exception as e:
        job.status = "failed"
        job.errors.append(f"Fatal error: {str(e)}")
        job.completed_at = datetime.now(timezone.utc).isoformat()
        print(f"💥 [{job_id}] Batch job failed: {e}")


def _aggregate_batch_results(results: list[dict]) -> dict:
    """Merge per-page grading results into a single consolidated result.

    - Combines questions from all pages (handles answers split across pages)
    - Sums total score
    - Averages confidence
    - Merges feedback lists
    """
    all_questions = []
    all_feedback = []
    total_score = 0.0
    total_max = 0.0
    confidence_sum = 0.0
    reg_no = "UNKNOWN"
    is_flagged = False

    for r in results:
        # Collect registration number from first page that has it
        if reg_no == "UNKNOWN":
            reg_no = (
                r.get("registration_number")
                or r.get("reg_no")
                or "UNKNOWN"
            ).upper()

        # Collect questions
        questions = r.get("questions", [])
        if questions:
            all_questions.extend(questions)

        # Sum scores
        score = r.get("score", 0)
        if isinstance(score, (int, float)):
            total_score += score

        max_marks = r.get("max_marks", r.get("total_marks", 0))
        if isinstance(max_marks, (int, float)):
            total_max += max_marks

        # Average confidence
        conf = r.get("confidence", 0)
        if isinstance(conf, (int, float)):
            confidence_sum += conf

        # Merge feedback
        fb = r.get("feedback", [])
        if isinstance(fb, list):
            all_feedback.extend(fb)

        # Any page flagged → whole submission flagged
        if r.get("is_flagged"):
            is_flagged = True

    return {
        "registration_number": reg_no,
        "score": round(total_score, 2),
        "max_marks": round(total_max, 2),
        "confidence": round(confidence_sum / max(len(results), 1), 3),
        "is_flagged": is_flagged,
        "questions": all_questions,
        "feedback": all_feedback,
        "pages_graded": len(results),
        "batch_mode": True,
    }


# ─── Batch Evaluate Endpoint ─────────────────────────────────

@app.post("/api/evaluate-batch")
async def evaluate_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user=Depends(require_auth),
):
    """
    Enterprise batch grading endpoint.

    Accepts multiple images and/or PDFs. Each PDF is split into
    per-page images at 300 DPI. All pages are graded asynchronously
    in the background. Returns a job_id for polling progress.

    Supported formats: JPEG, PNG, WEBP, PDF
    Max files: 20 | Max size per file: 15 MB
    """
    if not state.active_rubric_text:
        raise HTTPException(
            status_code=400,
            detail="No active rubric. Upload an Answer Key PDF via /api/setup-exam first.",
        )

    await _enforce_rate_limit(request, current_user, "evaluate_batch", max_requests=3, window_seconds=60)

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {MAX_BATCH_FILES} per batch.",
        )

    # ── Collect all pages (images + PDF→image conversions) ────
    pages: list[tuple[bytes, str]] = []
    filenames: list[str] = []

    for f in files:
        content_type = f.content_type or ""
        raw_bytes = await f.read()

        if len(raw_bytes) > MAX_BATCH_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File '{f.filename}' exceeds {MAX_BATCH_FILE_SIZE // (1024*1024)}MB limit.",
            )

        if content_type == "application/pdf" or (f.filename and f.filename.lower().endswith(".pdf")):
            # Convert PDF pages to images
            try:
                pdf_images = _pdf_to_images(raw_bytes)
                pages.extend(pdf_images)
                filenames.append(f"{f.filename} ({len(pdf_images)} pages)")
                print(f"📄 PDF '{f.filename}' → {len(pdf_images)} page images")
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to process PDF '{f.filename}': {str(e)}",
                )

        elif content_type.startswith("image/"):
            pages.append((raw_bytes, content_type))
            filenames.append(f.filename or "image")

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{content_type}' for '{f.filename}'. Use images or PDFs.",
            )

    if not pages:
        raise HTTPException(status_code=400, detail="No valid pages found in uploaded files.")

    # ── Auto-detect student from first page header ────────────
    detected_student: dict | None = None
    detected_reg_no: str | None = None
    try:
        first_img, first_mime = pages[0]
        if supabase:
            detected_student = await identify_and_match_student(
                image_bytes=first_img,
                mime_type=first_mime,
                supabase_client=supabase,
            )
            detected_reg_no = (
                (detected_student.get("student") or {}).get("reg_no")
                or (detected_student.get("header") or {}).get("reg_no")
            )
        else:
            header = await identify_student_from_header(first_img, first_mime)
            detected_student = {"header": header, "student": None, "assessment": None, "matched": False}
            detected_reg_no = header.get("reg_no")
        print(f"🔍 Auto-detected student: {detected_reg_no or 'UNKNOWN'}")
    except Exception as hdr_err:
        print(f"⚠️ Header auto-detect failed (non-blocking): {hdr_err}")

    # Extract assessment ID from auto-detection (if matched)
    detected_assessment_id: str | None = None
    if detected_student:
        detected_assessment_id = (detected_student.get("assessment") or {}).get("id")

    # ── Create job & launch background processing ─────────────
    job_id = str(uuid.uuid4())[:12]
    job = BatchJob(job_id=job_id, total_pages=len(pages), detected_student=detected_student)
    _batch_jobs[job_id] = job

    # Clean up old jobs (keep last 50)
    if len(_batch_jobs) > 50:
        oldest_keys = list(_batch_jobs.keys())[:-50]
        for k in oldest_keys:
            del _batch_jobs[k]

    background_tasks.add_task(_process_batch_job, job_id, pages, state.active_rubric_text, detected_reg_no, detected_assessment_id)

    print(f"🚀 Batch job {job_id} started — {len(pages)} pages from {len(files)} files")

    return {
        "status": "processing",
        "job_id": job_id,
        "total_pages": len(pages),
        "files": filenames,
        "detected_student": detected_student,
        "message": f"Batch grading started for {len(pages)} pages. Poll /api/batch-status/{job_id} for progress.",
    }


@app.get("/api/batch-status/{job_id}")
async def get_batch_status(job_id: str, current_user=Depends(require_auth)):
    """
    Polling endpoint for batch job progress.

    Returns current status, pages processed, and results when complete.
    The frontend polls this every 3-5 seconds until status is 'completed'.
    """
    job = _batch_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Batch job '{job_id}' not found.")

    response = {
        "job_id": job.job_id,
        "status": job.status,
        "total_pages": job.total_pages,
        "processed_pages": job.processed_pages,
        "progress_percent": round((job.processed_pages / max(job.total_pages, 1)) * 100, 1),
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "errors": job.errors,
        "detected_student": job.detected_student,
    }

    if job.status == "completed" and job.aggregated_result:
        response["result"] = job.aggregated_result
        response["per_page_results"] = job.results

    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
