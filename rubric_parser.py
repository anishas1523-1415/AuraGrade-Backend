"""
AuraGrade — Rubric Parser & PDF Answer Key Extractor
=====================================================
Extracts text from faculty-uploaded PDF answer keys and uses Gemini
to structure them into a machine-readable rubric JSON.

This is the core of the "Closed-Book Grading" architecture:
  - Faculty uploads their specific answer key / rubric as PDF
  - This module extracts the text content
  - Gemini structures it into per-question rubric with mark breakdowns
  - The structured rubric is stored in Supabase and injected into
    every grading prompt — making AuraGrade institution-agnostic

Why Closed-Book?
  - The AI is FORBIDDEN from using external/web knowledge
  - The ONLY source of truth is the faculty's answer key
  - This prevents syllabus mismatch (old vs new methods)
  - Guarantees institutional control over grading standards
"""

from __future__ import annotations

import json
import os
import io
from typing import Optional

from google import genai
from google.genai import types


# ---------------------------------------------------------------------------
#  Gemini client (injected from main.py)
# ---------------------------------------------------------------------------

_gemini_client: genai.Client | None = None


def get_parser_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _gemini_client


def set_parser_client(client: genai.Client):
    """Allow main.py to inject the shared Gemini client."""
    global _gemini_client
    _gemini_client = client


# ---------------------------------------------------------------------------
#  PDF Text Extraction (using PyMuPDF / fitz — blazingly fast & accurate)
# ---------------------------------------------------------------------------


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract all text content from a PDF file.
    Uses PyMuPDF (fitz) for high-speed, high-fidelity text extraction
    that preserves formatting, tables, and special characters.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            if text and text.strip():
                pages_text.append(f"--- Page {page_num + 1} ---\n{text.strip()}")

        doc.close()

        if not pages_text:
            return ""

        return "\n\n".join(pages_text)

    except ImportError:
        raise RuntimeError(
            "PyMuPDF is required for PDF extraction. "
            "Install it: pip install pymupdf"
        )
    except Exception as exc:
        raise RuntimeError(f"PDF extraction failed: {exc}")


def extract_rubric_from_pdf(file_path: str) -> str:
    """
    Convenience function: Takes a file path to a Professor's PDF
    Answer Key/Rubric, extracts all the text, and cleans it up
    for direct injection into the AI grading prompt.

    Returns a single cleaned string (excess whitespace collapsed)
    ready to be passed to generate_grader_prompt().
    """
    print(f"📄 Extracting text from Rubric PDF: {file_path}")
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        extracted_text = ""

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            extracted_text += page.get_text("text") + "\n"

        doc.close()

        # Clean up excess whitespace to save LLM tokens
        clean_text = " ".join(extracted_text.split())
        print(f"✅ Rubric successfully extracted! ({len(clean_text)} chars)")
        return clean_text

    except Exception as e:
        print(f"❌ Failed to parse PDF: {e}")
        return ""


def extract_text_from_pdf_image(pdf_bytes: bytes, mime_type: str = "application/pdf") -> str:
    """
    For scanned/handwritten PDFs where text extraction fails,
    use Gemini Vision to OCR the content directly.
    Sends the PDF as an image to Gemini and extracts all text.
    """
    client = get_parser_client()

    ocr_prompt = """You are a document OCR specialist. Extract ALL text content
from this document image/PDF. Preserve the structure:
- Question numbers and sub-parts
- Mark allocations (e.g., "2 marks", "[5M]", etc.)
- Answer content, formulas, diagrams descriptions
- Any rubric/marking scheme notes

Output the extracted text as-is, preserving headings and structure.
Do NOT summarize or interpret — just extract the raw text faithfully."""

    from gemini_retry import call_gemini

    response = call_gemini(
        client,
        model="gemini-3-flash-preview",
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type=mime_type),
            ocr_prompt,
        ],
        config=types.GenerateContentConfig(
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        ),
    )

    if response and response.text:
        return response.text.strip()
    return ""


# ---------------------------------------------------------------------------
#  AI-Powered Rubric Structuring (Gemini converts raw text → rubric JSON)
# ---------------------------------------------------------------------------

RUBRIC_STRUCTURE_PROMPT = """You are an expert exam rubric architect for a university grading system.

You have been given raw text extracted from a faculty member's official Answer Key / Rubric PDF.
Your job is to parse this into a STRUCTURED rubric that an AI grading engine can use.

## Rules
1. Identify each question/sub-question from the text.
2. For each question, extract:
   - The question title or topic
   - Maximum marks allocated
   - Specific marking breakdown (what earns each mark)
   - Critical penalties (common mistakes that MUST be penalised)
   - Key terms/concepts that MUST appear for full marks
3. If the answer key contains model answers, extract the expected answer content.
4. Preserve the faculty's EXACT grading intent — do not add your own criteria.
5. If marks are not explicitly stated, infer from context (e.g., "2M" = 2 marks).

## Output Format
Output strictly in JSON:
{
    "rubric": {
        "q1": {
            "title": "<question topic/title>",
            "max_marks": <int>,
            "breakdown": [
                "<what earns mark 1>",
                "<what earns mark 2>"
            ],
            "critical_penalties": [
                "<specific mistake to penalise and how many marks to deduct>"
            ],
            "key_terms": ["<term1>", "<term2>"],
            "model_answer_excerpt": "<the expected answer content if provided, otherwise empty string>"
        },
        "q2": { ... }
    },
    "total_marks": <int — sum of all max_marks>,
    "subject_detected": "<detected subject/course name if visible>",
    "exam_type_detected": "<IA1, IA2, Mid-Sem, End-Sem, Quiz, etc. if visible>",
    "model_answer_text": "<full model answer text extracted, for RAG indexing>"
}

## Important
- Use question keys like "q1", "q2", "q2a", "q2b" etc.
- If the PDF has both questions AND answers, extract both.
- If only answers are provided (no explicit questions), infer the question from the answer.
- critical_penalties should be empty [] if none are obvious.
- model_answer_excerpt per question should contain the specific expected answer.
- model_answer_text should contain ALL the answer content combined (for Pinecone RAG).

Here is the raw text from the faculty's PDF:

"""


async def structure_rubric_from_text(
    raw_text: str,
    subject_hint: str | None = None,
) -> dict:
    """
    Use Gemini to convert raw extracted text into a structured rubric JSON.

    Parameters
    ----------
    raw_text : str
        The raw text content extracted from the faculty's PDF.
    subject_hint : str, optional
        A hint about the subject (e.g., "Data Science") to help Gemini.

    Returns
    -------
    dict
        Structured rubric with per-question breakdowns, penalties, key terms.
    """
    client = get_parser_client()

    prompt = RUBRIC_STRUCTURE_PROMPT + raw_text

    if subject_hint:
        prompt += f"\n\n[HINT: This is for the subject: {subject_hint}]"

    from gemini_retry import call_gemini, parse_response

    response = call_gemini(
        client,
        model="gemini-3-flash-preview",
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    result = parse_response(response)

    if not result or not isinstance(result, dict):
        raise RuntimeError("Gemini could not structure the rubric from the provided text.")

    # Ensure required keys
    result.setdefault("rubric", {})
    result.setdefault("total_marks", 0)
    result.setdefault("subject_detected", subject_hint or "Unknown")
    result.setdefault("exam_type_detected", "Unknown")
    result.setdefault("model_answer_text", "")

    # Calculate total if not set
    if result["total_marks"] == 0:
        result["total_marks"] = sum(
            q.get("max_marks", 0) for q in result["rubric"].values()
        )

    return result


# ---------------------------------------------------------------------------
#  Full Pipeline: PDF bytes → structured rubric + model answer text
# ---------------------------------------------------------------------------


async def parse_answer_key_pdf(
    pdf_bytes: bytes,
    mime_type: str = "application/pdf",
    subject_hint: str | None = None,
) -> dict:
    """
    Complete pipeline: Faculty PDF → structured rubric JSON.

    1. Extracts text from PDF (PyPDF2 text extraction)
    2. If text extraction yields little/no content (scanned PDF),
       falls back to Gemini Vision OCR
    3. Structures the extracted text into rubric JSON via Gemini
    4. Returns the rubric + model answer text for storage

    Parameters
    ----------
    pdf_bytes : bytes
        Raw bytes of the uploaded PDF file.
    mime_type : str
        MIME type of the file (usually "application/pdf").
    subject_hint : str, optional
        Subject name to help the AI understand context.

    Returns
    -------
    dict
        {
            "rubric": { per-question rubric },
            "total_marks": int,
            "model_answer_text": str,
            "subject_detected": str,
            "exam_type_detected": str,
            "extraction_method": "text" | "vision_ocr",
            "raw_text": str,
            "raw_text_length": int,
        }
    """
    # Step 1: Try text extraction first (fast, no API cost)
    extraction_method = "text"
    raw_text = ""

    try:
        raw_text = extract_text_from_pdf(pdf_bytes)
    except RuntimeError:
        pass  # PyMuPDF not available or failed

    # Step 2: If text extraction got < 50 chars, try Vision OCR
    if len(raw_text.strip()) < 50:
        extraction_method = "vision_ocr"
        try:
            raw_text = extract_text_from_pdf_image(pdf_bytes, mime_type)
        except Exception as exc:
            raise RuntimeError(
                f"Could not extract text from PDF (both text and OCR failed): {exc}"
            )

    if not raw_text.strip():
        raise RuntimeError(
            "No text content could be extracted from the PDF. "
            "Ensure it contains readable text or is a clear scan."
        )

    # Step 3: Structure into rubric JSON
    structured = await structure_rubric_from_text(raw_text, subject_hint)

    # Add metadata
    structured["extraction_method"] = extraction_method
    structured["raw_text"] = raw_text
    structured["raw_text_length"] = len(raw_text)

    return structured
