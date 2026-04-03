from typing import Optional, List, Tuple, Any
import base64
import urllib.request
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from app.dependencies import get_supabase, get_grading_repo, get_batch_service
from app.services.batch_service import BatchService
from app.logging_config import get_logger
from app.repositories.grading_repository import GradingRepository
from app.core.state import get_exam_state
from app.utils.security import enforce_rate_limit, ensure_grade_access, is_staff_role
from auth_guard import require_auth, optional_auth
from evaluator import agentic_grade_stream
import json

router = APIRouter(prefix="/api", tags=["Grading"])
logger = get_logger("grading_router")

_evaluate_sse_idempotency_cache: dict[str, dict] = {}
EVALUATE_SSE_CACHE_MAX = 500
_grade_script_cache: dict[str, dict[str, Any]] = {}
GRADE_SCRIPT_CACHE_MAX = 200


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _normalize_annotation_box(note: dict[str, Any], idx: int) -> dict[str, Any] | None:
    # Prefer Gemini's canonical [ymin, xmin, ymax, xmax] box_2d (0..1000 scale).
    box_2d = note.get("box_2d")
    if isinstance(box_2d, list) and len(box_2d) >= 4:
        try:
            ymin, xmin, ymax, xmax = box_2d[:4]
            x = _to_float(xmin) / 10.0
            y = _to_float(ymin) / 10.0
            w = (_to_float(xmax) - _to_float(xmin)) / 10.0
            h = (_to_float(ymax) - _to_float(ymin)) / 10.0
        except Exception:
            x = y = w = h = None
    else:
        # Accept either percentage boxes, [0..1] normalized values, or pixel boxes.
        x = note.get("x", note.get("left", note.get("x_pct", note.get("x_percent"))))
        y = note.get("y", note.get("top", note.get("y_pct", note.get("y_percent"))))
        w = note.get("width", note.get("w", note.get("width_pct", note.get("w_pct"))))
        h = note.get("height", note.get("h", note.get("height_pct", note.get("h_pct"))))

    if x is None or y is None or w is None or h is None:
        return None

    xf = _to_float(x)
    yf = _to_float(y)
    wf = _to_float(w)
    hf = _to_float(h)

    if xf <= 1 and yf <= 1 and wf <= 1 and hf <= 1:
        xf, yf, wf, hf = xf * 100, yf * 100, wf * 100, hf * 100

    # Pixel-style fallback conversion when values exceed percentage range.
    if xf > 100 or yf > 100 or wf > 100 or hf > 100:
        img_w = _to_float(note.get("image_width", note.get("page_width", note.get("img_w"))), 0.0)
        img_h = _to_float(note.get("image_height", note.get("page_height", note.get("img_h"))), 0.0)
        if img_w > 0 and img_h > 0:
            xf = (xf / img_w) * 100.0
            yf = (yf / img_h) * 100.0
            wf = (wf / img_w) * 100.0
            hf = (hf / img_h) * 100.0
        elif max(xf, yf, wf, hf) <= 1000:
            # Common VLM coordinate scale.
            xf, yf, wf, hf = xf / 10.0, yf / 10.0, wf / 10.0, hf / 10.0

    points = note.get(
        "points",
        note.get(
            "marks_awarded",
            note.get("score_delta", note.get("mark_impact", note.get("impact", note.get("delta")))),
        ),
    )
    has_explicit_points = any(
        k in note for k in ("points", "marks_awarded", "score_delta", "mark_impact", "impact", "delta")
    )
    pf = _to_float(points, 0.0)

    explicit_type = str(note.get("type") or "").strip().lower()
    if explicit_type in {"key_term", "error", "diagram", "partial", "correction", "penalty"}:
        note_type = explicit_type
    else:
        note_type = ""

    is_correct = note.get("is_correct")
    if note_type:
        pass
    elif isinstance(is_correct, bool):
        note_type = "key_term" if is_correct else "error"
    else:
        note_type = "error" if pf < 0 else "key_term"

    # If model omitted numeric impact, infer a display-friendly default from type.
    if not has_explicit_points and abs(pf) < 1e-9:
        if note_type in {"error", "penalty"}:
            pf = -1.0
        else:
            pf = 1.0

    description = (
        note.get("description")
        or note.get("rationale")
        or note.get("reasoning")
        or note.get("reason")
        or note.get("justification")
        or note.get("verdict_note")
        or note.get("note")
        or note.get("comment")
        or note.get("explanation")
        or "AI mark reasoning"
    )

    # Legacy payloads often persist points=0 for clearly positive/negative tags.
    if abs(pf) < 1e-9 and note_type in {"key_term", "diagram", "partial", "correction", "error", "penalty"}:
        if note_type in {"error", "penalty"}:
            pf = -1.0
        else:
            pf = 1.0

    return {
        "id": str(note.get("id") or f"note_{idx}"),
        "type": note_type,
        "label": str(note.get("label") or note.get("question_number") or f"Q{idx + 1}"),
        "description": str(description),
        "points": pf,
        "x": max(0.0, min(100.0, xf)),
        "y": max(0.0, min(100.0, yf)),
        "width": max(2.0, min(100.0, wf)),
        "height": max(2.0, min(100.0, hf)),
    }


def _feedback_fallback_data_url(feedback: list[str]) -> str:
    lines = ["AuraGrade Script Snapshot"]
    for item in (feedback or [])[:10]:
        clean = str(item).replace("&", "and").replace("<", "").replace(">", "")
        lines.append(f"- {clean[:120]}")

    y = 36
    text_nodes = []
    for line in lines:
        text_nodes.append(f'<text x="20" y="{y}" font-family="monospace" font-size="14" fill="#1f2937">{line}</text>')
        y += 28

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600">'
        '<rect width="100%" height="100%" fill="#f8fafc"/>'
        '<rect x="12" y="12" width="1176" height="1576" fill="none" stroke="#cbd5e1" stroke-width="2"/>'
        + "".join(text_nodes)
        + "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _persist_script_artifacts(
    repo: GradingRepository,
    *,
    grade_id: str | None,
    student_id: str | None,
    assessment_id: str | None,
    image_src: str,
    annotations: list[dict[str, Any]],
) -> None:
    # Best-effort persistence across schema variants.
    if grade_id:
        try:
            repo.supabase.table("grades").update(
                {"image_url": image_src, "annotations": annotations}
            ).eq("id", grade_id).execute()
            return
        except Exception:
            pass

        # Schema-safe fallback: persist artifact payload in audit_logs metadata.
        try:
            repo.supabase.table("audit_logs").insert(
                {
                    "grade_id": grade_id,
                    "action": "SCRIPT_ARTIFACT",
                    "changed_by": "system",
                    "old_score": None,
                    "new_score": None,
                    "reason": "Script artifact snapshot persisted",
                    "metadata": {
                        "image_src": image_src,
                        "annotations": annotations,
                    },
                }
            ).execute()
            return
        except Exception:
            pass

    candidate_tables = ["answer_scripts", "submissions", "scripts", "graded_scripts"]
    for table_name in candidate_tables:
        try:
            payload: dict[str, Any] = {
                "image_url": image_src,
                "annotations": annotations,
            }
            if grade_id:
                payload["grade_id"] = grade_id
            if student_id:
                payload["student_id"] = student_id
            if assessment_id:
                payload["assessment_id"] = assessment_id
            repo.supabase.table(table_name).insert(payload).execute()
            return
        except Exception:
            continue


def _normalize_annotation_list(raw: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return normalized
    for i, note in enumerate(raw):
        if not isinstance(note, dict):
            continue
        mapped = _normalize_annotation_box(note, i)
        if mapped:
            normalized.append(mapped)
    return normalized

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
        latest_annotations: list[dict[str, Any]] = []
        try:
            async for event_str in agentic_grade_stream(
                image_bytes,
                mime_type=mime_type,
                dynamic_rubric_text=dynamic_rubric_text,
            ):
                yield event_str

                event_type = None
                payload_data: dict[str, Any] | None = None
                for line in event_str.split("\n"):
                    if line.startswith("event: "):
                        event_type = line.split("event: ", 1)[1].strip()
                    elif line.startswith("data: "):
                        try:
                            payload_data = json.loads(line.split("data: ", 1)[1])
                        except Exception:
                            payload_data = None

                if event_type in {"annotations", "pass1_partial", "annotation_verdict", "pass2_result"} and payload_data:
                    if isinstance(payload_data.get("annotations"), list):
                        latest_annotations = _normalize_annotation_list(payload_data.get("annotations"))
                    elif isinstance(payload_data.get("new_annotations"), list):
                        latest_annotations.extend(_normalize_annotation_list(payload_data.get("new_annotations")))
                    elif isinstance(payload_data.get("final_pass2_annotations"), list):
                        latest_annotations = _normalize_annotation_list(payload_data.get("final_pass2_annotations"))

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
                        grade_id_saved = saved_grade.get('id') if isinstance(saved_grade, dict) else None

                        image_src = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
                        _persist_script_artifacts(
                            repo,
                            grade_id=grade_id_saved,
                            student_id=(saved_grade or {}).get("student_id") if isinstance(saved_grade, dict) else None,
                            assessment_id=assessment_id,
                            image_src=image_src,
                            annotations=latest_annotations,
                        )

                        if grade_id_saved:
                            _grade_script_cache[grade_id_saved] = {
                                "image_src": image_src,
                                "annotations": latest_annotations,
                            }
                            if len(_grade_script_cache) > GRADE_SCRIPT_CACHE_MAX:
                                _grade_script_cache.pop(next(iter(_grade_script_cache)))

                        yield f"event: db\ndata: {json.dumps({
                            'saved': bool(saved_grade),
                            'grade_id': grade_id_saved,
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


@router.get("/grades/{grade_id}")
async def get_grade_endpoint(
    grade_id: str,
    reg_no: str | None = None,
    dob: str | None = None,
    current_user=Depends(optional_auth),
    repo: GradingRepository = Depends(get_grading_repo),
):
    """Fetch a single grade with access checks. Supports both JWT auth and student reg_no+DOB."""
    try:
        result = (
            repo.supabase.table("grades")
            .select("*, students(name, email, reg_no, dob), assessments(subject, title, rubric_json)")
            .eq("id", grade_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to fetch grade {grade_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch grade")

    grade = result.data
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    # Check access: either authenticated user or student with matching reg_no+DOB
    if current_user:
        ensure_grade_access(current_user, grade)
    elif reg_no and dob:
        # Student portal access - validate reg_no and DOB match
        if grade["students"]["reg_no"].upper() != reg_no.upper():
            raise HTTPException(status_code=403, detail="Access denied")
        try:
            from app.routers.student import _normalize_dob
            provided_dob = _normalize_dob(dob)
            stored_dob = _normalize_dob(str(grade["students"].get("dob") or ""))
            if provided_dob != stored_dob:
                raise HTTPException(status_code=403, detail="Access denied")
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    return grade


@router.get("/grades/{grade_id}/script")
async def get_grade_script_endpoint(
    grade_id: str,
    reg_no: str | None = None,
    dob: str | None = None,
    current_user=Depends(optional_auth),
    repo: GradingRepository = Depends(get_grading_repo),
):
    """Fetch the student script image and annotation boxes for result-view overlay. Supports both JWT auth and student reg_no+DOB."""
    try:
        grade_res = (
            repo.supabase.table("grades")
            .select("*, students(name, email, reg_no, dob)")
            .eq("id", grade_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to fetch grade {grade_id} script: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch script")

    grade = grade_res.data
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    # Check access: either authenticated user or student with matching reg_no+DOB
    if current_user:
        ensure_grade_access(current_user, grade)
    elif reg_no and dob:
        # Student portal access - validate reg_no and DOB match
        if grade["students"]["reg_no"].upper() != reg_no.upper():
            raise HTTPException(status_code=403, detail="Access denied")
        try:
            from app.routers.student import _normalize_dob
            provided_dob = _normalize_dob(dob)
            stored_dob = _normalize_dob(str(grade["students"].get("dob") or ""))
            if provided_dob != stored_dob:
                raise HTTPException(status_code=403, detail="Access denied")
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    image_src = None
    annotations: list[dict[str, Any]] = []

    # 1) Direct fields on grade row (if deployment has these columns)
    image_src = grade.get("image_url") or grade.get("script_url") or grade.get("image_src")
    raw_ann = grade.get("annotations") or grade.get("annotation_json") or grade.get("visual_annotations")
    if isinstance(raw_ann, str):
        try:
            raw_ann = json.loads(raw_ann)
        except Exception:
            raw_ann = None
    if isinstance(raw_ann, list):
        for i, note in enumerate(raw_ann):
            if isinstance(note, dict):
                normalized = _normalize_annotation_box(note, i)
                if normalized:
                    annotations.append(normalized)

    # 2) Probe artifact payload persisted in audit logs (schema-safe fallback)
    if not image_src and grade.get("id"):
        try:
            artifact_res = (
                repo.supabase.table("audit_logs")
                .select("metadata")
                .eq("grade_id", grade.get("id"))
                .eq("action", "SCRIPT_ARTIFACT")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            artifact_row = (artifact_res.data or [None])[0]
            metadata = (artifact_row or {}).get("metadata") or {}
            if isinstance(metadata, dict):
                image_src = metadata.get("image_src") or metadata.get("image_url")
                if not annotations and isinstance(metadata.get("annotations"), list):
                    for i, note in enumerate(metadata.get("annotations") or []):
                        if isinstance(note, dict):
                            normalized = _normalize_annotation_box(note, i)
                            if normalized:
                                annotations.append(normalized)
        except Exception:
            pass

    # 3) Probe candidate script tables when grade row does not carry image directly
    if not image_src:
        candidate_tables = ["answer_scripts", "submissions", "scripts", "graded_scripts"]
        grade_id_value = grade.get("id")
        student_id = grade.get("student_id")
        assessment_id = grade.get("assessment_id")
        reg_no = ((grade.get("students") or {}).get("reg_no") or "").upper()

        for table_name in candidate_tables:
            try:
                row = None

                # First, prefer exact grade linkage when available.
                if grade_id_value:
                    try:
                        row_res = (
                            repo.supabase.table(table_name)
                            .select("*")
                            .eq("grade_id", grade_id_value)
                            .limit(1)
                            .execute()
                        )
                        row = (row_res.data or [None])[0]
                    except Exception:
                        row = None

                # Next, match by student + assessment (latest if table supports created_at).
                if not row:
                    query = repo.supabase.table(table_name).select("*")
                    if student_id:
                        query = query.eq("student_id", student_id)
                    if assessment_id:
                        query = query.eq("assessment_id", assessment_id)
                    try:
                        row_res = query.order("created_at", desc=True).limit(1).execute()
                    except Exception:
                        row_res = query.limit(1).execute()
                    row = (row_res.data or [None])[0]

                if not row and reg_no:
                    reg_query = repo.supabase.table(table_name).select("*").eq("reg_no", reg_no)
                    try:
                        row_res = reg_query.order("created_at", desc=True).limit(1).execute()
                    except Exception:
                        row_res = reg_query.limit(1).execute()
                    row = (row_res.data or [None])[0]

                if not row:
                    continue

                image_src = (
                    row.get("image_url")
                    or row.get("script_url")
                    or row.get("image_src")
                    or row.get("preview_url")
                    or row.get("page_url")
                    or row.get("data_url")
                )

                if not annotations:
                    row_ann = row.get("annotations") or row.get("annotation_json") or row.get("visual_annotations")
                    if isinstance(row_ann, str):
                        try:
                            row_ann = json.loads(row_ann)
                        except Exception:
                            row_ann = None
                    if isinstance(row_ann, list):
                        for i, note in enumerate(row_ann):
                            if isinstance(note, dict):
                                normalized = _normalize_annotation_box(note, i)
                                if normalized:
                                    annotations.append(normalized)

                if image_src:
                    break
            except Exception:
                continue

    if not image_src:
        image_src = _feedback_fallback_data_url(grade.get("feedback") or [])

    # If artifact points to remote storage URL, convert to inline data URL so client render is stable.
    if isinstance(image_src, str) and image_src.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(image_src, timeout=8) as resp:
                raw = resp.read()
                mime = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip() or "image/jpeg"
            image_src = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        except Exception:
            image_src = _feedback_fallback_data_url(grade.get("feedback") or [])

    if not annotations:
        feedback = grade.get("feedback") or []
        if isinstance(feedback, list):
            for i, point in enumerate(feedback[:8]):
                text = str(point)
                lowered = text.lower()
                negative = (
                    "missing" in lowered
                    or "incorrect" in lowered
                    or "deduct" in lowered
                    or "penalty" in lowered
                    or "error" in lowered
                )
                annotations.append(
                    {
                        "id": f"fb_{i}",
                        "type": "error" if negative else "key_term",
                        "label": f"Q{i + 1}",
                        "description": text,
                        "points": -1.0 if negative else 1.0,
                        "x": 6.0,
                        "y": 8.0 + i * 10.0,
                        "width": 88.0,
                        "height": 8.0,
                    }
                )

    return {
        "status": "success",
        "script": {
            "image_src": image_src,
            "annotations": annotations,
        },
    }


@router.put("/grades/{grade_id}/approve")
async def approve_grade_endpoint(
    grade_id: str,
    current_user=Depends(require_auth),
    repo: GradingRepository = Depends(get_grading_repo),
):
    """Approve a grade (staff roles only)."""
    if not is_staff_role(current_user.get("role")):
        raise HTTPException(status_code=403, detail="Only staff can approve grades")

    try:
        existing = (
            repo.supabase.table("grades")
            .select("id, ai_score, prof_status")
            .eq("id", grade_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to load grade {grade_id} for approval: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch grade")

    grade = existing.data
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    reviewed_at = datetime.now(timezone.utc).isoformat()

    try:
        updated = (
            repo.supabase.table("grades")
            .update({"prof_status": "Approved", "reviewed_at": reviewed_at})
            .eq("id", grade_id)
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to approve grade {grade_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to approve grade")

    try:
        repo.supabase.table("audit_logs").insert(
            {
                "grade_id": grade_id,
                "action": "APPROVE",
                "changed_by": current_user.get("id") or "system",
                "old_score": grade.get("ai_score"),
                "new_score": grade.get("ai_score"),
                "reason": "Grade approved by staff",
                "metadata": {"previous_status": grade.get("prof_status")},
            }
        ).execute()
    except Exception:
        # Do not fail approval if audit log persistence is temporarily unavailable.
        pass

    return {"status": "success", "message": "Grade approved", "data": (updated.data or [{}])[0]}


@router.put("/grades/{grade_id}/appeal")
async def appeal_grade_endpoint(
    grade_id: str,
    reason: str = Query(..., min_length=2, max_length=2000),
    current_user=Depends(require_auth),
    repo: GradingRepository = Depends(get_grading_repo),
):
    """Submit an appeal on a grade (students can appeal their own grades; staff can flag)."""
    try:
        existing = (
            repo.supabase.table("grades")
            .select("id, ai_score, prof_status, students(email, reg_no)")
            .eq("id", grade_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to load grade {grade_id} for appeal: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch grade")

    grade = existing.data
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    ensure_grade_access(current_user, grade)

    reviewed_at = datetime.now(timezone.utc).isoformat()

    try:
        updated = (
            repo.supabase.table("grades")
            .update({"prof_status": "Flagged", "appeal_reason": reason.strip(), "reviewed_at": reviewed_at})
            .eq("id", grade_id)
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to submit appeal for grade {grade_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit appeal")

    try:
        repo.supabase.table("audit_logs").insert(
            {
                "grade_id": grade_id,
                "action": "APPEAL_SUBMIT",
                "changed_by": current_user.get("id") or "system",
                "old_score": grade.get("ai_score"),
                "new_score": grade.get("ai_score"),
                "reason": reason.strip(),
                "metadata": {"previous_status": grade.get("prof_status")},
            }
        ).execute()
    except Exception:
        pass

    return {"status": "success", "message": "Appeal submitted", "data": (updated.data or [{}])[0]}


@router.put("/grades/{grade_id}/override")
async def override_grade_endpoint(
    grade_id: str,
    new_score: float = Query(..., ge=0),
    reason: str = Query("Manual override", min_length=2, max_length=2000),
    current_user=Depends(require_auth),
    repo: GradingRepository = Depends(get_grading_repo),
):
    """Override a grade score (staff roles only)."""
    if not is_staff_role(current_user.get("role")):
        raise HTTPException(status_code=403, detail="Only staff can override grades")

    try:
        existing = (
            repo.supabase.table("grades")
            .select("id, ai_score, prof_status")
            .eq("id", grade_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to load grade {grade_id} for override: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch grade")

    grade = existing.data
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    reviewed_at = datetime.now(timezone.utc).isoformat()

    try:
        updated = (
            repo.supabase.table("grades")
            .update({"ai_score": new_score, "prof_status": "Overridden", "reviewed_at": reviewed_at})
            .eq("id", grade_id)
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to override grade {grade_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to override grade")

    try:
        repo.supabase.table("audit_logs").insert(
            {
                "grade_id": grade_id,
                "action": "OVERRIDE",
                "changed_by": current_user.get("id") or "system",
                "old_score": grade.get("ai_score"),
                "new_score": new_score,
                "reason": reason.strip(),
                "metadata": {"previous_status": grade.get("prof_status")},
            }
        ).execute()
    except Exception:
        pass

    return {"status": "success", "message": "Grade overridden", "data": (updated.data or [{}])[0]}

