import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Optional

from app.logging_config import get_logger
from app.repositories.grading_repository import GradingRepository
from evaluator import agentic_grade_stream

logger = get_logger("batch_service")

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
        self.detected_student = detected_student

class BatchService:
    def __init__(self, repo: GradingRepository):
        self.repo = repo
        self._jobs: Dict[str, BatchJob] = {}

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        return self._jobs.get(job_id)

    async def create_job(self, pages: List[Tuple[bytes, str]], rubric_text: str, detected_student: dict | None = None) -> str:
        job_id = str(uuid.uuid4())[:12]
        job = BatchJob(job_id=job_id, total_pages=len(pages), detected_student=detected_student)
        self._jobs[job_id] = job
        
        # Limit job history
        if len(self._jobs) > 100:
            oldest = next(iter(self._jobs))
            del self._jobs[oldest]
            
        # Launch background task (caller should use background_tasks.add_task)
        return job_id

    async def run_batch_job(self, job_id: str, pages: List[Tuple[bytes, str]], rubric_text: str, assessment_id: str = "DEMO_IA1"):
        job = self._jobs.get(job_id)
        if not job: return

        try:
            for i, (image_bytes, mime_type) in enumerate(pages):
                page_label = f"Page {i + 1}/{job.total_pages}"
                try:
                    page_result: dict | None = None
                    async for event_str in agentic_grade_stream(image_bytes, mime_type=mime_type, dynamic_rubric_text=rubric_text):
                        if event_str.startswith("event: result"):
                            data_line = event_str.split("data: ", 1)[1].split("\n")[0]
                            page_result = json.loads(data_line)
                    
                    if page_result:
                        page_result["_page_number"] = i + 1
                        job.results.append(page_result)
                    else:
                        job.errors.append(f"{page_label}: Empty result")
                except Exception as e:
                    job.errors.append(f"{page_label}: {str(e)}")
                    logger.error(f"Batch page failure: {e}")

                job.processed_pages = i + 1
                if i < len(pages) - 1:
                    await asyncio.sleep(1.5) # Throttling

            if job.results:
                job.aggregated_result = self._aggregate_results(job.results)
                
                # Persist to Supabase
                reg = job.aggregated_result.get("registration_number", "UNKNOWN")
                self.repo.save_grade(reg, assessment_id, job.aggregated_result)
                
            job.status = "completed"
        except Exception as e:
            job.status = "failed"
            job.errors.append(str(e))
        finally:
            job.completed_at = datetime.now(timezone.utc).isoformat()

    def _aggregate_results(self, results: List[dict]) -> dict:
        total_score = 0.0
        total_max = 0.0
        conf_sum = 0.0
        questions = []
        feedback = []
        reg_no = "UNKNOWN"
        
        for r in results:
            if reg_no == "UNKNOWN":
                reg_no = r.get("registration_number", "UNKNOWN")
            
            total_score += r.get("score", 0)
            total_max += r.get("max_marks", 0)
            conf_sum += r.get("confidence", 0)
            questions.extend(r.get("questions", []))
            feedback.extend(r.get("feedback", []))

        return {
            "registration_number": reg_no,
            "score": round(total_score, 2),
            "max_marks": round(total_max, 2),
            "confidence": round(conf_sum / max(len(results), 1), 3),
            "questions": questions,
            "feedback": feedback,
            "pages_graded": len(results),
            "batch_mode": True,
        }

    @staticmethod
    def pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> List[Tuple[bytes, str]]:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append((pix.tobytes("jpeg"), "image/jpeg"))
        doc.close()
        return images
