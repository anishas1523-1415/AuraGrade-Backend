"""
AuraGrade — Agentic Audit & Appeal Engine
==========================================
The "Supreme Court" of the grading pipeline.

When a student appeals a grade, this module invokes a **Higher-Reasoning
Audit Agent** (Head of Department persona) that:

1. Retrieves the original grade, rubric, and model-answer context.
2. Re-examines the AI feedback against the student's stated concern.
3. Cross-references with Pinecone RAG context for semantic validation.
4. Issues a binding verdict: Upheld, Adjusted Up, or Adjusted Down.

The audit is streamed as SSE events so the staff dashboard can render
the deliberation in real-time.

This module is designed to be publication-ready:
  - Demonstrates "Self-Correction" via multi-agent deliberation.
  - Provides XAI (Explainable AI) audit trail for Responsible AI claims.
  - Human-in-the-loop: professor must still approve the audit verdict.
"""

from __future__ import annotations

import json
import asyncio
from typing import AsyncGenerator

from google import genai
from google.genai import types

from evaluator import (
    get_gemini_client,
    retrieve_model_answer_context,
    _sse_event,
)


# ---------------------------------------------------------------------------
#  CORE — Audit Appeal Pipeline (SSE generator)
# ---------------------------------------------------------------------------


async def audit_appeal_stream(
    grade_data: dict,
    assessment_data: dict,
    student_comment: str,
    student_name: str = "Student",
) -> AsyncGenerator[str, None]:
    """
    The full audit-appeal pipeline, yielded as SSE events.

    Parameters
    ----------
    grade_data : dict
        The full grade row from Supabase (ai_score, confidence, feedback, etc.)
    assessment_data : dict
        The assessment row (subject, title, rubric_json, model_answer)
    student_comment : str
        The student's appeal reason / concern text.
    student_name : str
        Display name for the student.

    Events emitted
    ──────────────
    step          : real-time reasoning steps
    rag           : RAG retrieval status
    original      : original grade summary
    audit_result  : final audit verdict (JSON)
    done          : signals end of stream
    error         : any error
    """

    client = get_gemini_client()

    rubric = assessment_data.get("rubric_json") or {}
    rubric_text = json.dumps(rubric, indent=2) if rubric else "No rubric defined."
    model_answer = assessment_data.get("model_answer") or ""
    subject = assessment_data.get("subject", "Unknown Subject")
    title = assessment_data.get("title", "Unknown Assessment")

    original_score = grade_data.get("ai_score", 0)
    original_confidence = grade_data.get("confidence", 0)
    original_feedback = grade_data.get("feedback", [])
    assessment_id = grade_data.get("assessment_id")

    try:
        # ── Step 1: Case intake ───────────────────────────────────
        yield _sse_event("step", {
            "icon": "📋",
            "text": f"Appeal received from {student_name} — opening case file…",
            "phase": "intake",
        })
        await asyncio.sleep(0.3)

        yield _sse_event("original", {
            "score": original_score,
            "confidence": original_confidence,
            "feedback": original_feedback,
            "student_comment": student_comment,
        })

        # ── Step 2: Retrieve model-answer context from Pinecone ───
        yield _sse_event("step", {
            "icon": "📚",
            "text": "Retrieving model-answer reference from vector store…",
            "phase": "rag_retrieval",
        })

        rag_context = await retrieve_model_answer_context(
            student_comment,  # Use the appeal text as query for relevance
            assessment_id=assessment_id,
            top_k=5,
        )

        if rag_context:
            yield _sse_event("rag", {
                "status": "retrieved",
                "chunks": rag_context.count("---") + 1,
            })
        else:
            yield _sse_event("rag", {
                "status": "skipped",
                "reason": "No model answers indexed for this assessment",
            })

        await asyncio.sleep(0.2)

        # ── Step 3: The Audit Agent deliberation ──────────────────
        yield _sse_event("step", {
            "icon": "⚖️",
            "text": "Invoking Head of Department Audit Agent…",
            "phase": "audit_invoke",
        })

        rag_section = ""
        if rag_context:
            rag_section = f"""
## Model Answer Reference (from Pinecone RAG)
{rag_context}
"""

        model_answer_section = ""
        if model_answer:
            model_answer_section = f"""
## Professor's Model Answer (from Supabase)
{model_answer[:2000]}{"…" if len(model_answer) > 2000 else ""}
"""

        audit_prompt = f"""You are the **Head of Department** at a prestigious university, acting
as a third-party mediator for an AI-grading appeal. You must be fair, thorough,
and scholarly. Your decision is binding but will be reviewed by a human professor.

## Case Details
- **Subject**: {subject}
- **Assessment**: {title}
- **Student**: {student_name}

## Original AI Grade
- **Score**: {original_score} / 10
- **Confidence**: {original_confidence:.0%}
- **AI Feedback**:
{json.dumps(original_feedback, indent=2)}

## Student's Appeal
"{student_comment}"

## Evaluation Rubric
{rubric_text}

{model_answer_section}
{rag_section}

## Your Audit Mandate
As Head of Department, you must:

1. **Analyze the Student's Concern**: Is it valid? Does it point to a genuine
   grading error (e.g., AI missed synonyms, penalised correct alternate phrasing,
   ignored a valid logical leap, or failed to read a diagram)?

2. **Cross-Reference with Ground Truth**: Compare the original feedback against
   the Model Answer and Rubric. Did the AI correctly apply the marking criteria?

3. **Check for Common AI Mistakes**:
   - Synonym blindness (student used different but correct terminology)
   - Diagram/flowchart misreading
   - Partial credit not awarded for reasoning even when final answer differs
   - Strike-through / correction marks misinterpreted
   - Cultural or notational variations in handwriting

4. **Issue Your Verdict**:
   - "Upheld" — original grade stands, AI was correct
   - "Adjusted Up" — student's concern is valid, increase the score
   - "Adjusted Down" — audit found the original AI was too generous (rare)

5. **Provide Detailed Justification**: Explain your reasoning step by step so
   both the student and the supervising professor can follow your logic.

## Output Format (strict JSON)
{{
    "verdict": "Upheld" | "Adjusted Up" | "Adjusted Down",
    "adjusted_score": <float 0-10>,
    "adjusted_confidence": <float 0-1>,
    "justification": [
        "Step 1: Reviewed student concern — ...",
        "Step 2: Cross-referenced with model answer — ...",
        "Step 3: Rubric alignment check — ...",
        "Step 4: Checked for AI blind spots — ...",
        "Final verdict: ..."
    ],
    "rubric_breakdown": {{
        "<criterion_name>": {{
            "original": <float>,
            "audited": <float>,
            "note": "..."
        }}
    }},
    "recommendation": "<brief note to supervising professor>"
}}
"""

        yield _sse_event("step", {
            "icon": "🔍",
            "text": "Examining original AI feedback against rubric…",
            "phase": "audit_rubric_check",
        })
        await asyncio.sleep(0.2)

        yield _sse_event("step", {
            "icon": "🧠",
            "text": "Checking for synonym blindness & alternate phrasing…",
            "phase": "audit_semantic_check",
        })
        await asyncio.sleep(0.2)

        yield _sse_event("step", {
            "icon": "📐",
            "text": "Validating partial credit & diagram interpretation…",
            "phase": "audit_partial_credit",
        })

        # Call Gemini — using the most capable available model
        from gemini_retry import call_gemini_async, parse_response
        audit_response = await call_gemini_async(
            client,
            model="gemini-3-flash-preview",
            contents=[audit_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,  # Low temperature for consistent, fair audits
            ),
        )

        audit_result = parse_response(audit_response)

        # ── SAFETY NET ────────────────────────────────────────────
        if not audit_result or not isinstance(audit_result, dict):
            audit_result = {
                "verdict": "Upheld",
                "adjusted_score": original_score,
                "adjusted_confidence": original_confidence,
                "justification": [
                    "Audit agent could not produce a structured response.",
                    "Original grade is maintained pending manual professor review.",
                ],
                "rubric_breakdown": {},
                "recommendation": "Manual review required — audit agent encountered an issue.",
            }
            yield _sse_event("step", {
                "icon": "⚠️",
                "text": "Audit Agent response was incomplete — defaulting to Upheld",
                "phase": "audit_fallback",
            })

        # Ensure all required keys
        audit_result.setdefault("verdict", "Upheld")
        audit_result.setdefault("adjusted_score", original_score)
        audit_result.setdefault("adjusted_confidence", original_confidence)
        audit_result.setdefault("justification", [])
        audit_result.setdefault("rubric_breakdown", {})
        audit_result.setdefault("recommendation", "No additional notes.")

        await asyncio.sleep(0.3)

        # ── Step 4: Emit verdict ──────────────────────────────────
        verdict = audit_result["verdict"]
        new_score = audit_result["adjusted_score"]
        score_delta = new_score - original_score

        if verdict == "Adjusted Up":
            yield _sse_event("step", {
                "icon": "📈",
                "text": f"Verdict: {verdict} — Score adjusted {original_score} → {new_score}/10 (+{score_delta:.1f})",
                "phase": "verdict_up",
            })
        elif verdict == "Adjusted Down":
            yield _sse_event("step", {
                "icon": "📉",
                "text": f"Verdict: {verdict} — Score adjusted {original_score} → {new_score}/10 ({score_delta:+.1f})",
                "phase": "verdict_down",
            })
        else:
            yield _sse_event("step", {
                "icon": "⚖️",
                "text": f"Verdict: {verdict} — Original score {original_score}/10 stands",
                "phase": "verdict_upheld",
            })

        await asyncio.sleep(0.2)

        yield _sse_event("step", {
            "icon": "📝",
            "text": f"Recommendation to professor: {audit_result['recommendation'][:120]}",
            "phase": "recommendation",
        })

        yield _sse_event("step", {
            "icon": "✅",
            "text": "Audit complete — awaiting professor confirmation.",
            "phase": "audit_complete",
        })

        # ── Final payload ─────────────────────────────────────────
        yield _sse_event("audit_result", {
            **audit_result,
            "original_score": original_score,
            "score_changed": original_score != new_score,
        })

        yield _sse_event("done", {"status": "complete"})

    except Exception as exc:
        yield _sse_event("error", {"message": str(exc)})
        yield _sse_event("done", {"status": "error"})


# ---------------------------------------------------------------------------
#  Non-streaming convenience wrapper
# ---------------------------------------------------------------------------


async def audit_appeal_sync(
    grade_data: dict,
    assessment_data: dict,
    student_comment: str,
    student_name: str = "Student",
) -> dict:
    """
    Run the audit pipeline and return the final result dict (non-streaming).
    Used by the REST endpoint when SSE is not needed.
    """
    result = None

    async for event_str in audit_appeal_stream(
        grade_data=grade_data,
        assessment_data=assessment_data,
        student_comment=student_comment,
        student_name=student_name,
    ):
        if event_str.startswith("event: audit_result"):
            data_line = event_str.split("data: ", 1)[1].split("\n")[0]
            result = json.loads(data_line)
        elif event_str.startswith("event: error"):
            data_line = event_str.split("data: ", 1)[1].split("\n")[0]
            error_data = json.loads(data_line)
            raise RuntimeError(error_data.get("message", "Audit failed"))

    return result or {
        "verdict": "Upheld",
        "adjusted_score": grade_data.get("ai_score", 0),
        "adjusted_confidence": grade_data.get("confidence", 0),
        "justification": ["Audit produced no result — original grade maintained."],
        "rubric_breakdown": {},
        "recommendation": "Manual review required.",
    }
