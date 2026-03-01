"""
AuraGrade — Script Header Parser (Auto-ID Vision Agent)
========================================================
Uses a specialised Gemini prompt to extract the Student Register Number
and Subject Code directly from the top section of a scanned answer sheet.

This eliminates manual data-entry errors in high-volume exam workflows
and is a critical feature for institutional (CoE-approved) deployments.

Usage:
    from header_parser import identify_student_from_header

    result = await identify_student_from_header(image_bytes, mime_type="image/jpeg")
    # → {"reg_no": "21AD045", "subject_code": "CS301", "page_number": 1, "confidence": "HIGH"}
"""

from __future__ import annotations

import os
import json
from typing import Optional

from google import genai
from google.genai import types


# ---------------------------------------------------------------------------
#  Module-level client (shared with main.py via set_gemini_client if needed)
# ---------------------------------------------------------------------------

_client: Optional[genai.Client] = None


def get_header_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _client = genai.Client(api_key=api_key)
    return _client


def set_header_client(c: genai.Client) -> None:
    global _client
    _client = c


# ---------------------------------------------------------------------------
#  Core — Header Identification
# ---------------------------------------------------------------------------

HEADER_PROMPT = """You are a specialised Vision Agent for a university examination system.
Your ONLY task is to read the **top header section** of a scanned answer-sheet image
and extract administrative information.

Focus on the top ~20% of the image where institutional answer sheets typically print:
  • Student Register Number / Roll Number / Hall Ticket Number
  • Subject Code / Course Code
  • Page number (if visible)

## Rules
1. Extract EXACTLY what is written — do not infer or guess missing digits.
2. If any field is partially obscured, illegible, or absent, return "FLAG_FOR_MANUAL"
   for that field instead of guessing.
3. Register numbers often follow patterns like: 21AD045, 22CS112, RA2111003010045.
4. Subject codes often look like: CS301, AI504, 18CS51, MA201.
5. Ignore the actual answer content below the header.

## Output (strict JSON)
{
    "reg_no": "string — the student register number, or FLAG_FOR_MANUAL",
    "subject_code": "string — the subject/course code, or FLAG_FOR_MANUAL",
    "page_number": "int — page number if visible, or 1 if not found",
    "confidence": "HIGH | MEDIUM | LOW — your confidence in the extraction"
}
"""


async def identify_student_from_header(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Analyse the header of an answer-sheet image and extract reg_no + subject_code.

    Parameters
    ----------
    image_bytes : bytes
        The raw image data (JPEG, PNG, etc.)
    mime_type : str
        MIME type of the image.

    Returns
    -------
    dict
        Parsed header info with keys: reg_no, subject_code, page_number, confidence
    """
    client = get_header_client()

    from gemini_retry import call_gemini_async, parse_response
    response = await call_gemini_async(
        client,
        model="gemini-3-flash-preview",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            HEADER_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,  # Very low — we want deterministic extraction
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    result = parse_response(response)

    # Safety net
    if not result or not isinstance(result, dict):
        return {
            "reg_no": "FLAG_FOR_MANUAL",
            "subject_code": "FLAG_FOR_MANUAL",
            "page_number": 1,
            "confidence": "LOW",
            "error": "Vision model returned no structured output",
        }

    result.setdefault("reg_no", "FLAG_FOR_MANUAL")
    result.setdefault("subject_code", "FLAG_FOR_MANUAL")
    result.setdefault("page_number", 1)
    result.setdefault("confidence", "MEDIUM")

    return result


async def identify_and_match_student(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    supabase_client=None,
) -> dict:
    """
    End-to-end: parse header → look up student in Supabase → return matched record.

    Returns
    -------
    dict with keys:
        header: raw parsed header
        student: matched student row or None
        assessment: matched assessment row or None
        matched: bool
    """
    header = await identify_student_from_header(image_bytes, mime_type)

    response = {
        "header": header,
        "student": None,
        "assessment": None,
        "matched": False,
    }

    if not supabase_client:
        return response

    reg_no = header.get("reg_no", "")
    subject_code = header.get("subject_code", "")

    # Try to match student
    if reg_no and reg_no != "FLAG_FOR_MANUAL":
        try:
            student_row = (
                supabase_client.table("students")
                .select("id, reg_no, name, email")
                .eq("reg_no", reg_no)
                .single()
                .execute()
            )
            if student_row.data:
                response["student"] = student_row.data
        except Exception:
            pass

    # Try to match assessment by subject code
    if subject_code and subject_code != "FLAG_FOR_MANUAL":
        try:
            assessment_row = (
                supabase_client.table("assessments")
                .select("id, subject, title")
                .ilike("subject", f"%{subject_code}%")
                .limit(1)
                .execute()
            )
            if assessment_row.data:
                response["assessment"] = assessment_row.data[0]
        except Exception:
            pass

    response["matched"] = response["student"] is not None

    return response
