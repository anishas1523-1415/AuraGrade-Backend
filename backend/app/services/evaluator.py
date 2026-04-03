from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import os

# Initialize Gemini Client for Agentic Evaluation
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

# 1. Define the Strict JSON Schema for Frontend Visual Mapping
class VisualAnnotation(BaseModel):
    is_correct: bool = Field(description="True for Green Box, False for Red Box (Deduction)")
    rationale: str = Field(description="Short reason shown when staff/student taps the box")
    marks_awarded: float = Field(description="Marks given for this specific section")

class QuestionEvaluation(BaseModel):
    question_number: str
    total_marks: float
    visual_annotations: list[VisualAnnotation]

class EvaluationResult(BaseModel):
    final_score: float
    confidence_score: int = Field(description="0-100 confidence of the AI engine")
    per_question_breakdown: list[QuestionEvaluation]
    human_review_required: bool = Field(description="Flag true if handwriting is illegible")

async def evaluate_script_visually(image_bytes: bytes, rubric_text: str):
    """
    Evaluates a script and returns structured JSON guaranteed to map 
    directly to the frontend's <AnnotationOverlay /> component.
    """
    if client is None:
        raise RuntimeError("Evaluation Engine Failure: Gemini API Key not configured")

    prompt = f"""
    You are an elite academic evaluator. Grade the provided answer script image against this rubric:
    {rubric_text}
    
    You MUST output strict JSON. For every point evaluated, create a 'visual_annotation'.
    If a point is completely wrong, flag 'is_correct' as false (triggers Red Box) and explain why in 'rationale'.
    If correct, flag true (triggers Green Box).
    """

    try:
        # Call Gemini 1.5 Flash using Structured JSON Mode
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationResult,
                temperature=0.1 # Low temperature for deterministic, repeatable grading
            )
        )
        return response.parsed_content
    except Exception as e:
        raise RuntimeError(f"Evaluation Engine Failure: {e}")
