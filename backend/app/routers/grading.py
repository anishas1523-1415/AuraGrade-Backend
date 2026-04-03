from typing import Optional, List, Tuple
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from app.dependencies import get_supabase, get_grading_repo, get_batch_service
from app.services.batch_service import BatchService
from app.logging_config import get_logger
from app.repositories.grading_repository import GradingRepository
from app.core.state import get_exam_state
from app.utils.security import enforce_rate_limit
from auth_guard import require_auth
from evaluator import agentic_grade_stream
import json

router = APIRouter(prefix="/api", tags=["Grading"])
logger = get_logger("grading_router")

_evaluate_sse_idempotency_cache: dict[str, dict] = {}
EVALUATE_SSE_CACHE_MAX = 500

@router.post("/evaluate")
@router.post("/grade/stream")
@router.post("/grade")
async def evaluate_script_endpoint(
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: Optional[str] = Query(None),
    student_reg_no: Optional[str] = Query(None),
    assessment_id: Optional[str] = Query(None),
    current_user=Depends(require_auth),
    state=Depends(get_exam_state),
    repo: GradingRepository = Depends(get_grading_repo),
    batch_service: BatchService = Depends(get_batch_service),
):
    """Refactored streaming evaluation endpoint with structured error handling."""
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    await enforce_rate_limit(request, current_user, "evaluate", max_requests=6, window_seconds=60)

    idem_key = (idempotency_key or "").strip() or None
    if idem_key and idem_key in _evaluate_sse_idempotency_cache:
        cached = _evaluate_sse_idempotency_cache[idem_key]

        async def replay_generator():
            yield f"event: step\ndata: {json.dumps({'icon': '♻️', 'text': 'Idempotent replay: returning cached evaluation'})}\n\n"
            yield f"event: result\ndata: {json.dumps(cached.get('result', {}))}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'complete', 'idempotent_replay': True})}\n\n"

        return StreamingResponse(replay_generator(), media_type="text/event-stream")

    dynamic_rubric_text = state.active_rubric_text

    # Fallback for grading page: load rubric/model answer from selected assessment in DB.
    if not dynamic_rubric_text and assessment_id:
        try:
            assessment_res = (
                repo.supabase
                .table("assessments")
                .select("id, title, subject, model_answer, rubric_json")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
            assessment = assessment_res.data or {}
            model_answer = (assessment.get("model_answer") or "").strip()
            rubric_json = assessment.get("rubric_json")

            if model_answer:
                dynamic_rubric_text = model_answer
            elif rubric_json:
                dynamic_rubric_text = json.dumps(rubric_json, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed loading rubric from assessment {assessment_id}: {e}")

    if not dynamic_rubric_text:
        raise HTTPException(
            status_code=400,
            detail="No active rubric found. Upload rubric in Configure page or select assessment with saved model answer.",
        )

    raw_bytes = await file.read()
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()

    if content_type == "application/pdf" or filename.endswith(".pdf"):
        try:
            pdf_pages = batch_service.pdf_to_images(raw_bytes)
            if not pdf_pages:
                raise HTTPException(status_code=400, detail="PDF has no readable pages.")

            if len(pdf_pages) == 1:
                image_bytes, mime_type = pdf_pages[0]
            else:
                # Merge all pages into one tall image so grading sees the full script.
                import cv2
                import numpy as np

                strips = []
                for page_bytes, _ in pdf_pages:
                    arr = np.frombuffer(page_bytes, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        strips.append(img)

                if not strips:
                    raise HTTPException(status_code=400, detail="PDF pages could not be decoded.")

                max_w = max(s.shape[1] for s in strips)
                resized = []
                for s in strips:
                    if s.shape[1] != max_w:
                        scale = max_w / s.shape[1]
                        s = cv2.resize(s, (max_w, int(s.shape[0] * scale)))
                    resized.append(s)

                stitched = np.vstack(resized)
                ok, buf = cv2.imencode(".jpg", stitched, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    raise HTTPException(status_code=500, detail="Failed to encode multi-page PDF for grading.")

                image_bytes = buf.tobytes()
                mime_type = "image/jpeg"
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to process PDF in /evaluate: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail="Failed to process PDF. Please upload a valid PDF.")
    elif content_type.startswith("image/"):
        image_bytes = raw_bytes
        mime_type = file.content_type or "image/jpeg"
    else:
        raise HTTPException(status_code=400, detail="File must be an image or PDF.")

    async def event_generator():
        last_result = None
        try:
            async for event_str in agentic_grade_stream(
                image_bytes,
                mime_type=mime_type,
                dynamic_rubric_text=dynamic_rubric_text,
            ):
                yield event_str

                if event_str.startswith("event: result"):
                    try:
                        data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                        last_result = json.loads(data_line)
                        
                        # PERSIST TO SUPABASE via Repo
                        # Note: We need assessment_id. For now, we assume a default or get it from first page.
                        # In a full flow, the frontend passes assessment_id.
                        saved_grade = repo.save_grade(
                            student_reg_no=student_reg_no or last_result.get("registration_number", "UNKNOWN"),
                            assessment_id=assessment_id or "DEMO_IA1", # Fallback for legacy/demo
                            results=last_result
                        )
                        yield f"event: db\ndata: {json.dumps({
                            'saved': bool(saved_grade),
                            'grade_id': saved_grade.get('id') if isinstance(saved_grade, dict) else None,
                            'reason': None if saved_grade else 'Grade persistence failed or student/assessment mapping missing',
                        })}\n\n"
                    except Exception as e:
                        logger.error(f"Failed to parse or save result: {e}")


            if idem_key and last_result:
                if len(_evaluate_sse_idempotency_cache) >= EVALUATE_SSE_CACHE_MAX:
                    _evaluate_sse_idempotency_cache.pop(next(iter(_evaluate_sse_idempotency_cache)))
                _evaluate_sse_idempotency_cache[idem_key] = {"result": last_result}

        except Exception as e:
            logger.error(f"Evaluation stream error: {e}", exc_info=True)
            safe_msg = "An internal error occurred during evaluation."
            if "429" in str(e):
                safe_msg = "API quota exceeded. Please wait a minute."
                
            yield f"event: error\ndata: {json.dumps({'message': safe_msg})}\n\n"
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


@router.post("/evaluate-batch")
async def evaluate_batch_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user=Depends(require_auth),
    state=Depends(get_exam_state),
    batch_service: BatchService = Depends(get_batch_service),
):
    """Refactored batch grading endpoint. Supports PDF-to-Image conversion."""
    if not state.active_rubric_text:
        raise HTTPException(status_code=400, detail="No active rubric. Set up an Answer Key PDF first.")

    await enforce_rate_limit(request, current_user, "evaluate_batch", max_requests=3, window_seconds=60)

    pages: List[Tuple[bytes, str]] = []
    filenames: List[str] = []

    for f in files:
        raw_bytes = await f.read()
        content_type = (f.content_type or "").lower()
        if content_type == "application/pdf" or f.filename.lower().endswith(".pdf"):
            try:
                pdf_imgs = batch_service.pdf_to_images(raw_bytes)
                pages.extend(pdf_imgs)
                filenames.append(f"{f.filename} ({len(pdf_imgs)} pages)")
            except Exception as e:
                logger.error(f"Failed to process PDF {f.filename}: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to process PDF {f.filename}")
        elif content_type.startswith("image/"):
            pages.append((raw_bytes, content_type))
            filenames.append(f.filename)

    if not pages:
        raise HTTPException(status_code=400, detail="No valid pages found in uploaded files.")

    job_id = await batch_service.create_job(pages, state.active_rubric_text)
    background_tasks.add_task(batch_service.run_batch_job, job_id, pages, state.active_rubric_text)

    return {
        "status": "processing",
        "job_id": job_id,
        "total_pages": len(pages),
        "files": filenames,
        "message": f"Batch process started. Poll /api/grading/batch-status/{job_id} for progress.",
    }


@router.get("/batch-status/{job_id}")
async def get_batch_status_endpoint(
    job_id: str,
    current_user=Depends(require_auth),
    batch_service: BatchService = Depends(get_batch_service)
):
    """Get the status and results of a background batch job."""
    job = batch_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "total_pages": job.total_pages,
        "processed_pages": job.processed_pages,
        "progress_percent": round((job.processed_pages / max(job.total_pages, 1)) * 100, 1),
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "errors": job.errors,
        "result": job.aggregated_result
    }

