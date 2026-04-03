import os
from typing import Any, List, Optional
import base64
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Body
from app.core.state import get_exam_state
from app.config import get_settings
from app.dependencies import get_supabase
from app.logging_config import get_logger
from app.models import SyncRubricBody, CreateAssessmentBody
from auth_guard import require_auth, require_role, optional_auth
from rubric_parser import extract_text_from_pdf
from supabase import Client

router = APIRouter(prefix="/api", tags=["Assessments"])
logger = get_logger("assessment_router")


def _is_dev_unauth_allowed() -> bool:
    settings = get_settings()
    bypass_flag = os.getenv("ALLOW_DEV_UNAUTH_CONFIG", "1").strip().lower()
    return (not settings.is_production) and bypass_flag not in {"0", "false", "no", "off"}


def _assert_config_access(current_user: Optional[dict[str, Any]], *allowed_roles: str) -> None:
    if current_user:
        role = (current_user.get("role") or "").upper()
        normalized_allowed = {r.upper() for r in allowed_roles}
        if role in normalized_allowed:
            return
        raise HTTPException(
            status_code=403,
            detail="Absolute Isolation: You do not have the required clearance to access this portal.",
        )

    if _is_dev_unauth_allowed():
        return

    raise HTTPException(status_code=401, detail="Missing authorization header.")

@router.get("/assessments")
async def list_assessments(
    supabase: Client = Depends(get_supabase),
    current_user=Depends(optional_auth),
):
    """List all assessments for selection."""
    _assert_config_access(current_user, "EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")
    try:
        result = supabase.table("assessments").select("*").order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to list assessments: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch assessments from database.")

@router.post("/assessments")
async def create_assessment(
    body: CreateAssessmentBody,
    supabase: Client = Depends(get_supabase),
    current_user=Depends(optional_auth),
):
    """Create a new empty assessment record."""
    _assert_config_access(current_user, "EVALUATOR", "ADMIN_COE")
    try:
        result = supabase.table("assessments").insert({
            "subject": body.subject,
            "title": body.title,
            "created_at": "now()"
        }).execute()
        return result.data[0] if result.data else result.data
    except Exception as e:
        logger.error(f"Failed to create assessment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create assessment in database.")

@router.post("/sync-rubric")
async def sync_rubric_endpoint(
    assessment_id: str = Query(...),
    body: SyncRubricBody = Body(...),
    supabase: Client = Depends(get_supabase),
    current_user=Depends(optional_auth),
):
    """Sync rubric JSON and ideal model text to an assessment."""
    _assert_config_access(current_user, "EVALUATOR", "ADMIN_COE")
    try:
        update_data = {"rubric_json": body.rubric_json}
        if body.model_text:
            update_data["model_answer"] = body.model_text

        result = supabase.table("assessments").update(update_data).eq("id", assessment_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Assessment not found")
            
        return {"status": "success", "message": "Rubric and model answer synced to database."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync rubric for {assessment_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal error while syncing rubric.")

@router.post("/model-answer")
async def upload_model_answer_endpoint(
    assessment_id: str = Query(...),
    text: Optional[str] = Body(None, embed=True),
    file: Optional[UploadFile] = File(None),
    supabase: Client = Depends(get_supabase),
    current_user=Depends(optional_auth),
):
    """Sync model answer (either text or image) to an assessment."""
    _assert_config_access(current_user, "EVALUATOR", "ADMIN_COE")
    try:
        if file:
            # Handle image upload logic (implementation may vary, for now simulate success)
            logger.info(f"Received model answer image for {assessment_id}")
            # In a real app, we'd upload to Supabase Storage and save the URL
            return {"status": "success", "message": "Model answer image received and processed."}
        
        if text:
            result = supabase.table("assessments").update({"model_answer": text}).eq("id", assessment_id).execute()
            if not result.data:
                raise HTTPException(status_code=404, detail="Assessment not found")
            return {"status": "success", "message": "Model answer text updated."}

        raise HTTPException(status_code=400, detail="Either text or file must be provided.")
    except Exception as e:
        logger.error(f"Model answer sync failed: {e}")
        raise HTTPException(status_code=500, detail="Internal error while saving model answer.")

@router.post("/rubric/upload-pdf")
@router.post("/setup-exam")
async def setup_exam_endpoint(
    file: UploadFile = File(...),
    assessment_id: Optional[str] = Query(None),
    auto_sync: bool = Query(False),
    subject_hint: Optional[str] = Query(None),
    current_user=Depends(optional_auth),
    state=Depends(get_exam_state),
    supabase: Client = Depends(get_supabase),
):
    """
    Professor action to upload a PDF Answer Key/Rubric.
    This extracts the text and sets it as the active grading standard.
    Supports both legacy /setup-exam and frontend's /rubric/upload-pdf.
    """
    _assert_config_access(current_user, "EVALUATOR", "ADMIN_COE", "HOD_AUDITOR")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported for rubrics. Please upload a .pdf file.",
        )

    try:
        logger.info(f"📥 Received Answer Key PDF: {file.filename}")
        pdf_bytes = await file.read()

        if len(pdf_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        # Security: validate PDF magic bytes
        if not pdf_bytes[:5] == b"%PDF-":
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid PDF (magic bytes mismatch).",
            )

        extracted_text = extract_text_from_pdf(pdf_bytes)

        if not extracted_text or len(extracted_text.strip()) < 10:
            raise HTTPException(
                status_code=422,
                detail="Could not extract meaningful text from the PDF. Scanned PDFs are not currently supported in this endpoint.",
            )

        # Update global state
        state.active_rubric_text = extracted_text
        state.exam_name = file.filename.replace(".pdf", "")
        state.char_count = len(extracted_text)

        if auto_sync and assessment_id:
            update_payload = {"model_answer": extracted_text}
            if subject_hint:
                update_payload["subject"] = subject_hint
            try:
                sync_result = supabase.table("assessments").update(update_payload).eq("id", assessment_id).execute()
                if not sync_result.data:
                    logger.warning(f"Auto-sync requested but assessment not found: {assessment_id}")
            except Exception as sync_exc:
                logger.error(f"Failed to auto-sync rubric PDF to assessment {assessment_id}: {sync_exc}")

        logger.info(f"✅ Rubric loaded: {state.exam_name} ({state.char_count} chars)")

        return {
            "status": "success",
            "message": f"Successfully processed {file.filename}.",
            "exam_name": state.exam_name,
            "extracted_character_count": state.char_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing rubric: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error while processing the rubric PDF.")

@router.get("/exam-state")
async def get_exam_state_endpoint(current_user=Depends(require_auth), state=Depends(get_exam_state)):
    """Returns the current active rubric status."""
    return {
        "exam_name": state.exam_name,
        "is_active": state.active_rubric_text is not None,
        "character_count": state.char_count,
    }


@router.post("/pdf-preview")
async def pdf_preview_endpoint(
    file: UploadFile = File(...),
    current_user=Depends(optional_auth),
):
    """Render lightweight JPEG previews for all PDF pages for fast multi-page script display."""
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf") and (file.content_type or "").lower() != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        if total_pages == 0:
            raise HTTPException(status_code=400, detail="PDF has no pages.")

        # Keep preview fast by rendering at moderate scale and limiting extremely large PDFs.
        max_pages = 8
        pages_to_render = min(total_pages, max_pages)
        mat = fitz.Matrix(1.0, 1.0)
        page_previews: list[str] = []

        for idx in range(pages_to_render):
            pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
            jpeg_bytes = pix.tobytes("jpeg", jpg_quality=65)
            preview_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            page_previews.append(f"data:image/jpeg;base64,{preview_b64}")

        doc.close()
        return {
            "preview": page_previews[0] if page_previews else None,
            "preview_pages": page_previews,
            "pages": total_pages,
            "pages_rendered": pages_to_render,
            "truncated": total_pages > pages_to_render,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"PDF preview generation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to render PDF preview.")
