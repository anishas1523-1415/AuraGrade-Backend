import os
import io
import json
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from supabase import create_client, Client
from typing import Optional, List
import base64

from auth_guard import require_auth, require_role, optional_auth

from evaluator import (
    agentic_grade_stream,
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

app = FastAPI()

# Enable CORS for your Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("CORS_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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


# ─── Health Check ─────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"status": "AuraGrade AI Engine is Online. Ready for IA-1 bundles."}


# ─── Setup Exam: Professor Uploads Answer Key PDF ────────────

@app.post("/api/setup-exam")
async def setup_exam(file: UploadFile = File(...)):
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
async def get_exam_state():
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
async def evaluate_script(file: UploadFile = File(...)):
    """
    Simplified SSE endpoint for quick evaluations without student/assessment context.
    Accepts an image upload and streams the full agentic grading pipeline back.

    If a rubric has been uploaded via /api/setup-exam, it will be used as the
    grading standard (closed-book). Otherwise falls back to the default rubric.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")

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
                        reg = (
                            final_data.get("registration_number")
                            or final_data.get("reg_no")
                            or "UNKNOWN"
                        ).upper()
                        db.save(reg, final_data)
                        print(f"💾 Saved result for {reg} to MockDatabase")
                    except Exception as parse_err:
                        print(f"⚠️  Could not save result to MockDB: {parse_err}")

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
        "prof_status": "Pending",
    }

    response = (
        supabase.table("grades")
        .upsert(data, on_conflict="student_id,assessment_id")
        .execute()
    )
    return response.data


# ─── Routes ───────────────────────────────────────────────────

@app.post("/api/grade")
async def grade_paper(
    file: UploadFile = File(...),
    student_reg_no: Optional[str] = Query(None, description="Student register number"),
    assessment_id: Optional[str] = Query(None, description="Assessment UUID"),
    user=Depends(require_auth),
):
    try:
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
                "status": "QUOTA_EXHAUSTED",
                "feedback": ["⚠️ API quota full. Please wait 60 seconds and try again."],
                "is_flagged": True,
                "saved_to_db": False,
                "grade_id": None,
            }
        return {
            "score": 0.0,
            "confidence": 0.0,
            "status": "ERROR",
            "feedback": [f"System error: {err_msg}"],
            "is_flagged": True,
            "saved_to_db": False,
            "grade_id": None,
        }


# ─── NEW: Agentic SSE Streaming Endpoint ─────────────────────

@app.post("/api/grade/stream")
async def grade_paper_stream(
    file: UploadFile = File(...),
    student_reg_no: Optional[str] = Query(None, description="Student register number"),
    assessment_id: Optional[str] = Query(None, description="Assessment UUID"),
):
    """
    Agentic two-pass grading with Server-Sent Events.

    The frontend opens this as an EventSource-compatible stream.
    Events: step, pass1, rag, pass2, result, error, done
    """
    image_bytes = await file.read()

    # Determine MIME type
    content_type = file.content_type or "image/jpeg"

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

        # After stream completes — persist to Supabase
        if final_result and student_reg_no and assessment_id:
            try:
                db_record = save_grade_to_db(
                    student_reg_no, assessment_id, final_result
                )
                if db_record:
                    yield f"event: db\ndata: {json.dumps({'saved': True, 'grade_id': db_record[0]['id']})}\n\n"
                else:
                    yield f"event: db\ndata: {json.dumps({'saved': False, 'reason': 'Student not found — routed to Exception Handling Dashboard'})}\n\n"
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


# ─── Pydantic models ─────────────────────────────────────────

from pydantic import BaseModel
from typing import Optional as Opt


class SyncRubricBody(BaseModel):
    rubric_json: dict
    model_text: Opt[str] = None


class CreateAssessmentBody(BaseModel):
    subject: str
    title: str


# ─── Sync Rubric & Model Answer (Ground Truth) ───────────────

@app.post("/api/sync-rubric")
async def sync_rubric(
    assessment_id: str = Query(..., description="Assessment UUID"),
    body: SyncRubricBody = ...,
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


# ─── Create Assessment ───────────────────────────────────────

@app.post("/api/assessments")
async def create_assessment(body: CreateAssessmentBody):
    """Create a new assessment."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")

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
async def list_students():
    """List all students."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = supabase.table("students").select("*").order("reg_no").execute()
    return result.data


@app.get("/api/students/{reg_no}/grades")
async def get_student_grades(reg_no: str):
    """Get all grades for a student by register number."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    # First find the student
    student = (
        supabase.table("students")
        .select("id, reg_no, name, email")
        .eq("reg_no", reg_no)
        .single()
        .execute()
    )
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")

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


@app.get("/api/students/{reg_no}")
async def get_student(reg_no: str):
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
async def create_student(body: StudentCreate, user=Depends(require_auth)):
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
async def bulk_create_students(body: StudentBulkCreate, user=Depends(require_auth)):
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
async def delete_student(reg_no: str, user=Depends(require_auth)):
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
    user=Depends(require_auth),
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
async def resolve_exception(exception_id: str, body: ResolveExceptionBody, user=Depends(require_auth)):
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
async def list_assessments():
    """List all assessments."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    result = supabase.table("assessments").select("*").order("created_at", desc=True).execute()
    return result.data


# ─── Grades endpoints ────────────────────────────────────────

@app.get("/api/grades")
async def list_grades(
    status: Optional[str] = Query(None, description="Filter by prof_status"),
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
async def get_grade(grade_id: str):
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
    return result.data


@app.put("/api/grades/{grade_id}/approve")
async def approve_grade(grade_id: str, user=Depends(require_role("ADMIN_COE", "HOD_AUDITOR", "EVALUATOR"))):
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
        changed_by="professor",
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
async def appeal_grade(grade_id: str, reason: str = Query(..., description="Reason for appeal")):
    """Student appeals a grade — flags it for professor review."""
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
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
        changed_by="student",
    )
    return {"message": "Appeal submitted — professor will be notified", "data": result.data[0]}


# ─── Audit Appeal System (The "Supreme Court") ───────────────

@app.post("/api/audit-appeal/{grade_id}")
async def run_audit_appeal(grade_id: str):
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
async def run_audit_appeal_stream(grade_id: str):
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


# ─── Script Header Parser (Auto-ID Vision Agent) ─────────────

@app.post("/api/parse-header")
async def parse_script_header(
    file: UploadFile = File(...),
    match_db: bool = Query(True, description="Try to match reg_no against Supabase students"),
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
async def audit_log_stats():
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
async def admin_recent_activity(limit: int = Query(20)):
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
async def preview_ledger(assessment_id: str):
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
async def list_ledger_hashes(assessment_id: str):
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
async def get_lock_status(assessment_id: str):
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
async def get_student_results(reg_no: str):
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
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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
async def get_batch_status(job_id: str):
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
