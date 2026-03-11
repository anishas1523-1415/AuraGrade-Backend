"""
AuraGrade — Agentic Evaluation Engine v2
=========================================
Three-pass "Self-Correction" grading pipeline with Diagram Intelligence
and Semantic Gap Analysis post-processing.

Pass 0  ➜  "Diagram Agent"      : Detect & validate handwritten diagrams → Mermaid.js
Pass 1  ➜  "Grader Agent"       : Gemini Vision grades (with diagram context injected)
Pass 2  ➜  "Professor Audit"    : Gemini Reasoning audits & corrects Pass 1
RAG     ➜  Pinecone retrieval   : fetch model-answer context before grading
Post    ➜  Gap Analysis Sync    : update class-wide knowledge map incrementally
Each step yields SSE events so the frontend can render the Agentic Reasoning
Loop in real-time.
"""

from __future__ import annotations

import json
import os
import asyncio
from typing import AsyncGenerator, Optional

from google import genai
from google.genai import types

from image_processor import deskew_and_enhance, process_image_async
from gemini_retry import call_gemini, call_gemini_async, parse_response, QuotaExhaustedError, get_quota_wait_seconds, _rotate_client


# ---------------------------------------------------------------------------
#  Pinecone (lazy — only initialised when PINECONE_API_KEY is set)
# ---------------------------------------------------------------------------

_pinecone_index = None


def _get_pinecone_index():
    """Lazily initialise and return the Pinecone index."""
    global _pinecone_index
    if _pinecone_index is not None:
        return _pinecone_index

    api_key = os.environ.get("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX", "auragrade")

    if not api_key:
        return None

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)
        _pinecone_index = pc.Index(index_name)
        return _pinecone_index
    except Exception as exc:
        print(f"⚠️  Pinecone init failed: {exc}")
        return None


# ---------------------------------------------------------------------------
#  Gemini client (shared with main.py if imported, else standalone)
# ---------------------------------------------------------------------------

_gemini_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY")
        )
    return _gemini_client


def set_gemini_client(client: genai.Client):
    """Allow main.py to inject the already-initialised client."""
    global _gemini_client
    _gemini_client = client


# ---------------------------------------------------------------------------
#  Supabase client (injected from main.py for gap analysis post-processing)
# ---------------------------------------------------------------------------

_supabase_client = None


def set_evaluator_supabase(sb_client):
    """Allow main.py to inject the Supabase client for post-process sync."""
    global _supabase_client
    _supabase_client = sb_client


def get_evaluator_supabase():
    return _supabase_client


# ---------------------------------------------------------------------------
#  BM25 encoder (lazy — only initialised when pinecone-text is installed)
# ---------------------------------------------------------------------------

_bm25_encoder = None


def _get_bm25_encoder():
    """Lazily initialise and return the BM25 encoder for sparse vectors."""
    global _bm25_encoder
    if _bm25_encoder is not None:
        return _bm25_encoder

    try:
        from pinecone_text.sparse import BM25Encoder

        _bm25_encoder = BM25Encoder().default()
        print("✅ BM25 encoder initialised — hybrid search enabled")
        return _bm25_encoder
    except ImportError:
        print("⚠️  pinecone-text not installed — falling back to dense-only search")
        return None
    except Exception as exc:
        print(f"⚠️  BM25 init failed: {exc}")
        return None


# ---------------------------------------------------------------------------
#  RAG: retrieve model-answer context from Pinecone (hybrid search)
# ---------------------------------------------------------------------------


async def retrieve_model_answer_context(
    query_text: str,
    assessment_id: str | None = None,
    top_k: int = 3,
) -> str:
    """
    Query Pinecone for the most relevant model-answer chunks.

    Uses an alpha-blended hybrid search strategy:
    - Dense vector (semantic): understands meaning / concepts
    - Sparse vector (BM25): enforces exact keyword & syntax matching

    Falls back to Pinecone's integrated embedding if BM25 is unavailable.
    Returns a merged string of matching passages, or "" if Pinecone is off.
    """
    index = _get_pinecone_index()
    if index is None:
        return ""

    try:
        bm25 = _get_bm25_encoder()

        if bm25 is not None:
            # ── Hybrid Search: Dense + Sparse (BM25) ──────────────
            # Generate sparse vector for exact keyword matching
            sparse_vector = bm25.encode_queries(query_text)

            # Use Pinecone's integrated embedding for dense + BM25 sparse
            # The index.search() API handles dense automatically; we add sparse.
            # Fall back to query() if the index supports explicit vectors.
            try:
                results = index.search(
                    namespace="__default__",
                    query={
                        "top_k": top_k,
                        "inputs": {"text": query_text},
                        "sparse_vector": sparse_vector,
                    },
                    fields=["text", "assessment_id", "chunk_index"],
                )

                passages = []
                for hit in results.get("result", {}).get("hits", []):
                    fields = hit.get("fields", {})
                    if assessment_id and fields.get("assessment_id") != assessment_id:
                        continue
                    text_val = fields.get("text", "")
                    if text_val:
                        passages.append(text_val)

                if passages:
                    return "\n---\n".join(passages)
            except Exception:
                # If hybrid search param isn't supported by this index,
                # fall through to the standard path below
                pass

        # ── Fallback: Dense-only integrated embedding search ──────
        results = index.search(
            namespace="__default__",
            query={"top_k": top_k, "inputs": {"text": query_text}},
            fields=["text", "assessment_id", "chunk_index"],
        )

        passages = []
        for hit in results.get("result", {}).get("hits", []):
            fields = hit.get("fields", {})
            if assessment_id and fields.get("assessment_id") != assessment_id:
                continue
            text_val = fields.get("text", "")
            if text_val:
                passages.append(text_val)

        return "\n---\n".join(passages)
    except Exception as exc:
        print(f"⚠️  Pinecone search failed: {exc}")
        return ""


# ---------------------------------------------------------------------------
#  RAG: upsert a model answer into Pinecone (integrated embedding)
# ---------------------------------------------------------------------------


async def upsert_model_answer(
    assessment_id: str,
    text: str,
    chunk_size: int = 500,
):
    """
    Split `text` into chunks and upsert into Pinecone.
    The integrated embedding model (llama-text-embed-v2) computes vectors
    automatically from the `text` field — no manual embedding needed.
    """
    index = _get_pinecone_index()
    if index is None:
        raise RuntimeError("Pinecone is not configured (PINECONE_API_KEY missing)")

    # Simple fixed-size chunking
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    records = []
    for idx, chunk in enumerate(chunks):
        records.append(
            {
                "_id": f"{assessment_id}_{idx}",
                "text": chunk,
                "assessment_id": assessment_id,
                "chunk_index": idx,
            }
        )

    # upsert_records: Pinecone embeds the `text` field automatically
    index.upsert_records(namespace="__default__", records=records)
    return len(records)


# ---------------------------------------------------------------------------
#  Coordinate mapping: Gemini box_2d → frontend percentages
# ---------------------------------------------------------------------------

def map_to_frontend_coords(box_2d: list) -> dict:
    """Convert Gemini's [ymin, xmin, ymax, xmax] (0-1000) → frontend % coords."""
    if not box_2d or len(box_2d) < 4:
        return {"x": 0, "y": 0, "width": 10, "height": 5}
    ymin, xmin, ymax, xmax = box_2d[:4]
    return {
        "x": round(xmin / 10, 2),
        "y": round(ymin / 10, 2),
        "width": round(max((xmax - xmin) / 10, 2), 2),
        "height": round(max((ymax - ymin) / 10, 2), 2),
    }


# ---------------------------------------------------------------------------
#  SSE event helper
# ---------------------------------------------------------------------------

def _sse_event(event: str, data: dict) -> str:
    """Format a single Server-Sent Events frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
#  Dynamic Prompt Generator — Subject-Agnostic Grading Engine
# ---------------------------------------------------------------------------

def generate_grader_prompt(
    dynamic_rubric_text: str,
    rag_section: str = "",
    diagram_context: str = "",
) -> str:
    """
    Dynamically generates the Pass 1 grader system prompt based on
    whatever rubric the professor uploaded — Data Science, English
    Literature, Quantum Physics, Mechanical Engineering, anything.

    This is the core of AuraGrade's subject-agnostic architecture.
    The AI is given ONLY this rubric as its source of truth — no web
    search, no external knowledge, pure closed-book grading.

    Parameters
    ----------
    dynamic_rubric_text : str
        The rubric content (JSON or plain text from the professor's PDF).
    rag_section : str
        Optional RAG context retrieved from Pinecone.
    diagram_context : str
        Optional diagram validation context from Pass 0.

    Returns
    -------
    str
        The complete grader prompt ready to send to Gemini.
    """
    return f"""You are an expert University Professor evaluating an Internal Assessment.
You are strict, highly accurate, and leave no room for bias.

## ⛔ CLOSED-BOOK GRADING PROTOCOL ⛔
You are operating in CLOSED-BOOK MODE. This is NON-NEGOTIABLE:
- You MUST grade ONLY based on the Official Answer Key & Rubric provided below.
- You MUST NOT use any external knowledge, web information, or your own training data to judge answers.
- If a student writes something that is technically correct according to general knowledge,
  but does NOT match what the rubric specifies, it does NOT earn marks.
- The rubric below is the SOLE source of truth — it represents what the professor taught
  in their specific course module.
- If the rubric says "1 mark for X", then ONLY X earns that mark. No substitutions.

IMPORTANT: The image may be rotated or sideways. Rotate your internal
understanding to read the text horizontally if needed. Do NOT penalise
for image orientation — focus only on the written content.

## Step 1: Extract Student Identity
Read the top header of the answer sheet and extract the Registration Number (Reg.No).
Common patterns: AD010, 21AD045, RA2111003010045. If illegible, set as "FLAG_FOR_MANUAL".

## Step 2: Grade Per Question — OFFICIAL ANSWER KEY & RUBRIC
--- OFFICIAL ANSWER KEY & RUBRIC ---
{dynamic_rubric_text}
------------------------------------

**CRITICAL PENALTY RULES**: For any question with "critical_penalties" defined above,
you MUST check for those specific mistakes and apply the deductions automatically.
**KEY TERM MATCHING**: For any question with "key_terms" defined, the student MUST use
those specific terms (or close synonyms) to earn full marks.
**MODEL ANSWER REFERENCE**: If "model_answer_excerpt" is provided for a question,
compare the student's answer STRICTLY against it — not against your own knowledge.

## Step 3: Fairness Guidelines (within Closed-Book bounds)
- If the handwriting is messy but the logic is correct PER THE RUBRIC, award the marks.
- Crossed-out text = student self-corrected → give credit for the FINAL answer only.
- Diagrams: Check arrows, labels, and logical flow, not artistic quality.
- Do NOT award marks for "correct general knowledge" that the rubric doesn't ask for.
- Grade exactly what the rubric specifies — no more, no less.

{rag_section}
{diagram_context}
## Multimodal Analysis Instructions
When evaluating the handwritten script, pay close attention to:
1. **Handwriting Layout**: Identify headings, numbered points, and paragraph structure.
2. **Strike-throughs & Corrections**: Crossed-out text may indicate the student self-corrected — give credit for the final answer, not the struck-through one.
3. **Diagrams & Flowcharts**: Check if arrows, labels, and logic flow are correct.
4. **Key Terms Detection**: Identify all technical/domain terms the student used and count them.
5. **Confidence Indicators**: Underlines, bold strokes, or rewritten words suggest the student is confident about those answers.
6. **Critical Penalty Scan**: Actively look for common mistakes defined in the rubric's critical_penalties fields.

## Output Format
Output your response strictly in the following JSON format:
{{{{
    "registration_number": "<extracted Reg.No or FLAG_FOR_MANUAL>",
    "per_question_scores": {{{{
        "q1_score": <float>,
        "q2_score": <float>
    }}}},
    "score": <float — total of all per-question scores>,
    "confidence": <float 0-1>,
    "confidence_score": <integer 0-100 — percentage reflecting how confident you are in this evaluation based on handwriting clarity and answer ambiguity>,
    "human_review_required": <boolean — set to true if confidence_score is below 80>,
    "detected_key_terms": ["term1", "term2"],
    "penalties_applied": [
        "<description of any critical penalty applied>"
    ],
    "justification_note": "<concise explanation of exactly why marks were deducted, mentioning specific errors or missing elements>",
    "feedback": [
        "Detected N key terms: ...",
        "Layout analysis: ...",
        "Conceptual clarity: ...",
        "Accuracy check: ...",
        "Presentation quality: ...",
        "Critical penalty check: ..."
    ],
    "is_flagged": <boolean — true if handwriting is unreadable or logic is suspicious>,
    "spatial_annotations": [
        {{{{
            "type": "key_term | error | diagram | partial | correction | penalty",
            "label": "<short label>",
            "description": "<brief justification for the marking>",
            "points": <float — mark impact, positive or negative>,
            "box_2d": [<ymin>, <xmin>, <ymax>, <xmax>]
        }}}}
    ]
}}}}

## Spatial Annotation Guidelines
For the "spatial_annotations" array, you MUST visually locate regions in the handwritten script image.
Use Gemini's native bounding-box coordinate format:
- **box_2d**: [ymin, xmin, ymax, xmax] where each value is 0-1000 (normalised to image dimensions).
  - (0, 0) = top-left corner, (1000, 1000) = bottom-right corner.
- Annotate EVERY notable region (3-10 annotations):
  - **key_term**: a correctly used technical/domain term (positive points).
  - **error**: an incorrect statement, wrong formula, or factual mistake (negative points).
  - **diagram**: a handwritten diagram, flowchart, or figure.
  - **partial**: a region deserving partial credit (partially correct reasoning).
  - **correction**: a strike-through or self-correction by the student.
  - **penalty**: a region where a critical penalty was applied (negative points).
- Be precise with box_2d — tightly bound the relevant text or drawing.
"""


# ---------------------------------------------------------------------------
#  CORE — Agentic Grading Pipeline (SSE generator)
# ---------------------------------------------------------------------------


async def agentic_grade_stream(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    rubric: dict | None = None,
    assessment_id: str | None = None,
    student_reg_no: str | None = None,
    dynamic_rubric_text: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    The full two-pass agentic grading pipeline, yielded as SSE events.

    Parameters
    ----------
    image_bytes : bytes
        The student answer sheet image.
    mime_type : str
        MIME type of the image.
    rubric : dict | None
        Structured rubric JSON (from Supabase). Takes priority if provided.
    assessment_id : str | None
        Assessment UUID for DB persistence & RAG retrieval.
    student_reg_no : str | None
        Student register number for DB persistence.
    dynamic_rubric_text : str | None
        Raw rubric text extracted from the professor's PDF (via /api/setup-exam).
        Used when no structured `rubric` dict is available.
        This is the core of subject-agnostic grading — the text is injected
        directly into the prompt, making the AI grade any subject.

    Events emitted
    ──────────────
    step      : real-time reasoning step shown in the UI
    pass1     : raw Pass-1 grader result (JSON)
    rag       : RAG context retrieved (or skipped)
    pass2     : final audited result (JSON)
    result    : final merged result used by the frontend
    error     : any error during the pipeline
    done      : signals end of stream
    """

    client = get_gemini_client()

    # ── Rubric Resolution Priority ─────────────────────────────
    # 1. Structured rubric dict (from Supabase) → serialise to JSON text
    # 2. Raw rubric text (from professor's PDF upload) → use directly
    # 3. Neither → fall back to a generic rubric (demo mode)
    if rubric is not None:
        rubric_text = json.dumps(rubric, indent=2)
    elif dynamic_rubric_text:
        rubric_text = dynamic_rubric_text
    else:
        # Fallback demo rubric — only used when no rubric is configured at all
        rubric_text = json.dumps({
            "q1": {
                "title": "Define a Neural Network",
                "max_marks": 2,
                "breakdown": [
                    "1 mark for stating it is a computational model inspired by the human brain.",
                    "1 mark for mentioning the structure (organized in layers/neurons).",
                ],
            },
            "q2": {
                "title": "Python Pandas code to filter a dataframe",
                "max_marks": 5,
                "breakdown": [
                    "2 marks for correct Pandas syntax (e.g., df[...]).",
                    "3 marks for the correct logical condition using the bitwise operator `&`.",
                ],
                "critical_penalties": [
                    "If the student uses the word `and` instead of `&`, deduct 2 marks immediately as this causes a ValueError in Pandas.",
                ],
            },
            "q3": {
                "title": "Draw a basic CNN architecture",
                "max_marks": 8,
                "breakdown": [
                    "4 marks for the correct sequence: Input -> Conv2D -> MaxPooling -> Flatten -> Dense/FC -> Output.",
                    "4 marks for clear text labels on each block. Deduct marks proportionally for missing layers.",
                ],
            },
        }, indent=2)

    # ── Pre-processing: auto-rotate & enhance for better OCR ───
    processed_bytes = await process_image_async(image_bytes)

    try:
        # ── Step 0: PASS 0 — Diagram-to-Code Validation ───────────
        #   Runs FIRST so the AI "understands" any diagram logic
        #   before assigning marks. This is the key insight for
        #   "Atmost Accuracy" — logic over OCR.
        yield _sse_event("step", {
            "icon": "📐",
            "text": "Pass 0 — Diagram Detection Agent scanning for visual structures…",
            "phase": "diagram_detect",
        })
        await asyncio.sleep(0.05)

        diagram_result = None
        diagram_context = ""  # injected into grader prompt

        try:
            from vision_logic import detect_diagrams, validate_diagram_logic

            detection = await detect_diagrams(image_bytes, mime_type)

            if detection.get("has_diagram"):
                diagrams = detection.get("diagrams", [])
                diagram_types = ", ".join(d.get("type", "unknown") for d in diagrams)
                yield _sse_event("step", {
                    "icon": "🔍",
                    "text": f"Detected {len(diagrams)} diagram(s): {diagram_types}",
                    "phase": "diagram_found",
                })
                yield _sse_event("diagram_detect", {
                    "has_diagram": True,
                    "diagrams": diagrams,
                })
                await asyncio.sleep(0.05)

                yield _sse_event("step", {
                    "icon": "💻",
                    "text": "Converting handwritten diagram to Mermaid.js code…",
                    "phase": "diagram_convert",
                })

                diagram_result = await validate_diagram_logic(image_bytes, mime_type)

                if diagram_result.get("is_valid"):
                    yield _sse_event("step", {
                        "icon": "✅",
                        "text": f"Diagram logic validated — score: {diagram_result.get('logic_score', 0)}/10",
                        "phase": "diagram_valid",
                    })
                else:
                    flaws = diagram_result.get("logic_flaws", [])
                    yield _sse_event("step", {
                        "icon": "⚠️",
                        "text": f"Diagram has {len(flaws)} logic flaw(s) — score: {diagram_result.get('logic_score', 0)}/10",
                        "phase": "diagram_flaws",
                    })

                yield _sse_event("diagram_result", {
                    "has_diagram": True,
                    **diagram_result,
                })

                # Build the diagram context string for injection into grader prompt
                mermaid = diagram_result.get("mermaid_code", "")
                d_type = diagram_result.get("diagram_type", "unknown")
                d_score = diagram_result.get("logic_score", 0)
                d_valid = diagram_result.get("is_valid", False)
                d_flaws = diagram_result.get("logic_flaws", [])
                d_intent = diagram_result.get("student_intent", "")

                flaw_lines = ""
                for f in d_flaws[:5]:
                    flaw_lines += f"  - [{f.get('severity', 'Unknown')}] {f.get('flaw', '')}: {f.get('suggestion', '')}\n"

                diagram_context = f"""
## Diagram Logic Validation (Pass 0 — Pre-Grading Analysis)
A {d_type} diagram was detected and automatically converted to code.
- **Mermaid.js Code**:
```mermaid
{mermaid}
```
- **Logic Score**: {d_score}/10
- **Structurally Valid**: {"Yes" if d_valid else "No"}
- **Student Intent**: {d_intent}
{f"- **Logic Flaws Found**:\n{flaw_lines}" if d_flaws else "- No structural flaws detected."}

IMPORTANT: Use this validated diagram logic when evaluating the student's
answer. Give credit for correct logic even if the handwriting is messy.
Deduct marks for genuine logic flaws identified above.
"""

            else:
                yield _sse_event("step", {
                    "icon": "📝",
                    "text": "No diagrams detected — script is text-only.",
                    "phase": "diagram_skip",
                })
        except Exception as diag_exc:
            yield _sse_event("step", {
                "icon": "⚠️",
                "text": f"Diagram validation skipped: {str(diag_exc)[:80]}",
                "phase": "diagram_error",
            })

        # ── Step 1: Extracting handwriting ────────────────────────
        yield _sse_event("step", {
            "icon": "🔍",
            "text": "Extracting handwriting using Document AI…",
            "phase": "extract",
        })
        await asyncio.sleep(0.1)  # let the UI render

        # ── Step 2: RAG — retrieve model-answer context ───────────
        yield _sse_event("step", {
            "icon": "📚",
            "text": "Cross-referencing with Model Answer in vector store…",
            "phase": "rag",
        })

        rag_context = await retrieve_model_answer_context(
            "student answer evaluation",
            assessment_id=assessment_id,
        )

        if rag_context:
            yield _sse_event("rag", {
                "status": "retrieved",
                "chunks": rag_context.count("---") + 1,
            })
        else:
            yield _sse_event("rag", {
                "status": "skipped",
                "reason": "Pinecone not configured or no model answers indexed",
            })

        await asyncio.sleep(0.05)

        # ── Step 3: PASS 1 — Grader Agent ─────────────────────────
        yield _sse_event("step", {
            "icon": "🤖",
            "text": "Pass 1 — Grader Agent evaluating answer script…",
            "phase": "pass1",
        })

        rag_section = ""
        if rag_context:
            rag_section = f"""
## Model Answer Reference (retrieved from knowledge base)
{rag_context}
"""

        grader_prompt = generate_grader_prompt(
            dynamic_rubric_text=rubric_text,
            rag_section=rag_section,
            diagram_context=diagram_context,
        )

        pass1_response = None
        for _attempt in range(4):
            try:
                pass1_response = await call_gemini_async(
                    client,
                    model="gemini-3-flash-preview",
                    contents=[
                        types.Part.from_bytes(data=processed_bytes, mime_type="image/jpeg"),
                        grader_prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                    ),
                )
                break  # success
            except QuotaExhaustedError as qe:
                if _attempt >= 3:
                    raise
                wait_secs = max(qe.wait_seconds, 15)
                remaining = wait_secs
                while remaining > 0:
                    yield _sse_event("step", {
                        "icon": "⏳",
                        "text": f"API quota reached — waiting {int(remaining)}s for reset… (retry {_attempt + 2}/4)",
                        "phase": "quota_wait",
                    })
                    await asyncio.sleep(min(5, remaining))
                    remaining -= 5
                refreshed = _rotate_client()
                if refreshed:
                    client = refreshed
                yield _sse_event("step", {
                    "icon": "🔄",
                    "text": "Retrying Grader Agent…",
                    "phase": "quota_retry",
                })

        # ── SAFETY NET: handle None / exception / malformed ───────
        pass1_result = parse_response(pass1_response)

        if not pass1_result or not isinstance(pass1_result, dict):
            pass1_result = {
                "score": 0.0,
                "confidence": 0.0,
                "feedback": [
                    "⚠️ AI could not parse the handwritten script (possible quota limit).",
                    "Wait 60 seconds and try again, or ensure the image is clear.",
                ],
                "is_flagged": True,
                "detected_key_terms": [],
            }
            yield _sse_event("step", {
                "icon": "⚠️",
                "text": "Grader Agent could not parse response — API quota may be exhausted",
                "phase": "pass1_fallback",
            })

        pass1_result.setdefault("score", 0.0)
        pass1_result.setdefault("confidence", 0.0)
        pass1_result.setdefault("confidence_score", round(pass1_result.get("confidence", 0.0) * 100))
        pass1_result.setdefault("human_review_required", pass1_result.get("confidence_score", 0) < 80)
        pass1_result.setdefault("feedback", [])
        pass1_result.setdefault("is_flagged", False)
        pass1_result.setdefault("detected_key_terms", [])
        pass1_result.setdefault("spatial_annotations", [])
        pass1_result.setdefault("registration_number", student_reg_no or "FLAG_FOR_MANUAL")
        pass1_result.setdefault("per_question_scores", {})
        pass1_result.setdefault("penalties_applied", [])
        pass1_result.setdefault("justification_note", "")

        # ── DETERMINISTIC MATH: Never trust LLM's total score ─────
        # LLMs are reasoning engines, not calculators. Recalculate
        # the total from per-question scores using Python arithmetic.
        pq = pass1_result.get("per_question_scores", {})
        if pq and isinstance(pq, dict):
            calculated_total = round(sum(
                float(v) for v in pq.values() if isinstance(v, (int, float))
            ), 2)
            if calculated_total != pass1_result["score"]:
                pass1_result["_llm_raw_score"] = pass1_result["score"]
                pass1_result["score"] = calculated_total

        yield _sse_event("pass1", pass1_result)

        # Emit per-question breakdown and penalties for the UI
        pq_scores = pass1_result.get("per_question_scores", {})
        if pq_scores:
            yield _sse_event("step", {
                "icon": "📝",
                "text": f"Per-Q scores: {', '.join(f'{k}={v}' for k, v in pq_scores.items())}",
                "phase": "per_question",
            })

        penalties = pass1_result.get("penalties_applied", [])
        if penalties:
            yield _sse_event("step", {
                "icon": "🚨",
                "text": f"Critical penalties applied: {'; '.join(penalties[:3])}",
                "phase": "penalties",
            })

        # Emit annotation overlay data for the frontend canvas
        # Convert Gemini box_2d [ymin,xmin,ymax,xmax] (0-1000) → frontend %
        # Stream annotations incrementally via pass1_partial for reduced perceived latency
        raw_annotations = pass1_result.get("spatial_annotations", [])
        indexed_annotations = []
        if raw_annotations and isinstance(raw_annotations, list):
            for i, ann in enumerate(raw_annotations):
                if isinstance(ann, dict):
                    coords = map_to_frontend_coords(ann.get("box_2d", []))
                    annotation_obj = {
                        "id": f"ann_{i}",
                        "type": ann.get("type", "key_term"),
                        "label": ann.get("label", f"Region {i+1}"),
                        "description": ann.get("description", ""),
                        "points": ann.get("points", 0),
                        "reviewState": "pending",
                        **coords,
                    }
                    indexed_annotations.append(annotation_obj)
                    # Emit each annotation individually for box-by-box streaming
                    yield _sse_event("pass1_partial", {
                        "new_annotations": [annotation_obj],
                    })
                    await asyncio.sleep(0.05)  # stagger for visual effect
            # Also emit the full batch for backward compatibility
            if indexed_annotations:
                yield _sse_event("annotations", {"annotations": indexed_annotations})

        # Emit granular sub-steps from Pass 1
        key_terms = pass1_result.get("detected_key_terms", [])
        if key_terms:
            yield _sse_event("step", {
                "icon": "🔑",
                "text": f"Detected {len(key_terms)} key terms: {', '.join(key_terms[:6])}{'…' if len(key_terms) > 6 else ''}",
                "phase": "key_terms",
            })

        yield _sse_event("step", {
            "icon": "📊",
            "text": f"Pass 1 complete — initial score: {pass1_result['score']}/10 (confidence {pass1_result['confidence']:.0%})",
            "phase": "pass1_done",
        })

        await asyncio.sleep(0.1)

        # ── Step 4: PASS 2 — Professor Audit Agent ────────────────
        yield _sse_event("step", {
            "icon": "🔬",
            "text": "Pass 2 — Professor Audit Agent verifying grade…",
            "phase": "pass2",
        })

        # Build diagram summary for audit context
        diagram_audit_note = ""
        if diagram_result:
            d_score = diagram_result.get('logic_score', 0)
            d_valid = diagram_result.get('is_valid', False)
            d_type = diagram_result.get('diagram_type', 'unknown')
            d_flaws_count = len(diagram_result.get('logic_flaws', []))
            diagram_audit_note = f"""
## Diagram Intelligence Report (Pass 0)
A {d_type} diagram was validated via Mermaid.js code conversion.
- Logic Score: {d_score}/10 | Valid: {"Yes" if d_valid else "No"} | Flaws: {d_flaws_count}
- Verify the grader used this analysis correctly when awarding diagram-related marks.
"""

        # Build annotation context for the audit prompt
        annotation_context = ""
        if indexed_annotations:
            ann_summary = json.dumps(
                [{"id": a["id"], "type": a["type"], "label": a["label"],
                  "description": a["description"], "points": a["points"]}
                 for a in indexed_annotations],
                indent=2,
            )
            annotation_context = f"""
## Spatial Annotations from Pass 1 (review each)
The grader identified these regions on the answer sheet:
{ann_summary}
For EACH annotation, verify whether the label, type, and point value are correct.
Return your verdict per annotation in the "annotation_verdicts" array.
"""

        audit_prompt = f"""You are a senior professor auditing an AI-generated grade.
You MUST be strict and thorough — your job is to catch mistakes.

## ⛔ CLOSED-BOOK AUDIT PROTOCOL ⛔
You are auditing in CLOSED-BOOK MODE:
- Verify the grade ONLY against the rubric below — NOT against your own knowledge.
- If the grader awarded marks for content not in the rubric, flag it.
- If the grader missed marks for content that IS in the rubric, correct it.
- The rubric is the SOLE source of truth. No external knowledge applies.

IMPORTANT: The image may be rotated or sideways. Rotate your internal
understanding to read the text horizontally if needed.

## Original Grading (Pass 1)
{json.dumps({k: v for k, v in pass1_result.items() if k != 'spatial_annotations'}, indent=2)}

## Rubric Used
{rubric_text}
{diagram_audit_note}
{annotation_context}
## Audit Checklist
1. **Rubric Alignment**: Does the score STRICTLY match the rubric? Add up marks per criterion.
2. **Handwritten Nuances**: Did the grader miss strike-throughs, margin notes, or corrected answers?
3. **Diagram Logic**: Are flowchart arrows and labels validated against the expected answer?
4. **Partial Credit**: Did the grader miss opportunities to award partial marks for correct reasoning even if the final answer is wrong?
5. **Key Term Verification**: Cross-check detected terms for accuracy.
6. **Annotation Review**: For each Pass 1 annotation, confirm or correct the marking.
7. **Final Verdict**: State if the grade is Confirmed, Adjusted Up, or Adjusted Down.

Output strictly in JSON:
{{
    "score": <float 0-10>,
    "confidence": <float 0-1>,
    "feedback": [
        "Rubric alignment: ...",
        "Nuance check: ...",
        "Partial credit: ...",
        "Final verdict: Confirmed/Adjusted"
    ],
    "is_flagged": <boolean>,
    "audit_notes": "<brief summary of what you checked/changed>",
    "annotation_verdicts": [
        {{
            "id": "ann_0",
            "verdict": "confirmed | adjusted | rejected",
            "adjusted_points": <float or null — new points if adjusted>,
            "note": "<brief reason for verdict>"
        }}
    ]
}}
"""

        yield _sse_event("step", {
            "icon": "📋",
            "text": "Running rubric alignment check…",
            "phase": "audit_rubric",
        })

        # Signal that Pass 2 is reviewing annotations (turn boxes yellow)
        if indexed_annotations:
            reviewing_ids = [a["id"] for a in indexed_annotations]
            yield _sse_event("annotation_review", {
                "ids": reviewing_ids,
                "state": "reviewing",
            })
            # Also emit pass2_audit for the predictive UI streaming pattern
            yield _sse_event("pass2_audit", {
                "auditing_ids": reviewing_ids,
            })

        # Brief pause before next API call
        await asyncio.sleep(0.5)

        pass2_response = None
        for _attempt in range(4):
            try:
                pass2_response = await call_gemini_async(
                    client,
                    model="gemini-3-flash-preview",
                    contents=[
                        types.Part.from_bytes(data=processed_bytes, mime_type="image/jpeg"),
                        audit_prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                    ),
                )
                break  # success
            except QuotaExhaustedError as qe:
                if _attempt >= 3:
                    raise
                wait_secs = max(qe.wait_seconds, 15)
                remaining = wait_secs
                while remaining > 0:
                    yield _sse_event("step", {
                        "icon": "⏳",
                        "text": f"API quota reached — waiting {int(remaining)}s for reset… (retry {_attempt + 2}/4)",
                        "phase": "quota_wait",
                    })
                    await asyncio.sleep(min(5, remaining))
                    remaining -= 5
                refreshed = _rotate_client()
                if refreshed:
                    client = refreshed
                yield _sse_event("step", {
                    "icon": "🔄",
                    "text": "Retrying Audit Agent…",
                    "phase": "quota_retry",
                })

        # ── SAFETY NET: handle None / exception / malformed ───────
        pass2_result = parse_response(pass2_response)

        if not pass2_result or not isinstance(pass2_result, dict):
            # If audit fails, trust Pass 1 results
            pass2_result = {
                **{k: v for k, v in pass1_result.items() if k != "detected_key_terms"},
                "audit_notes": "Audit agent failed to respond — Pass 1 result used as-is.",
            }
            yield _sse_event("step", {
                "icon": "⚠️",
                "text": "Audit Agent could not parse response — trusting Pass 1",
                "phase": "pass2_fallback",
            })

        pass2_result.setdefault("score", pass1_result["score"])
        pass2_result.setdefault("confidence", pass1_result["confidence"])
        pass2_result.setdefault("feedback", pass1_result["feedback"])
        pass2_result.setdefault("is_flagged", pass1_result["is_flagged"])
        pass2_result.setdefault("audit_notes", "No corrections needed.")
        pass2_result.setdefault("annotation_verdicts", [])

        yield _sse_event("pass2", pass2_result)

        # Emit per-annotation verdicts so the UI can turn boxes green/red
        verdicts = pass2_result.get("annotation_verdicts", [])
        if verdicts and isinstance(verdicts, list):
            yield _sse_event("annotation_verdict", {"verdicts": verdicts})

            # Build final merged annotations with verdicts applied
            final_annotations = []
            for ann in indexed_annotations:
                v = next((vd for vd in verdicts if vd.get("id") == ann["id"]), None)
                merged = {**ann}
                if v:
                    merged["reviewState"] = v.get("verdict", "confirmed")
                    if v.get("adjusted_points") is not None:
                        merged["points"] = v["adjusted_points"]
                    if v.get("note"):
                        merged["verdictNote"] = v["note"]
                else:
                    merged["reviewState"] = "confirmed"
                final_annotations.append(merged)
            yield _sse_event("pass2_result", {
                "final_pass2_annotations": final_annotations,
            })

        audit_notes = pass2_result.get("audit_notes", "No corrections needed.")
        score_changed = pass1_result["score"] != pass2_result["score"]

        if score_changed:
            yield _sse_event("step", {
                "icon": "✏️",
                "text": f"Audit adjusted score: {pass1_result['score']} → {pass2_result['score']}/10",
                "phase": "pass2_correction",
            })
        else:
            yield _sse_event("step", {
                "icon": "✅",
                "text": f"Audit confirmed score: {pass2_result['score']}/10 — {audit_notes}",
                "phase": "pass2_confirmed",
            })

        await asyncio.sleep(0.05)

        yield _sse_event("step", {
            "icon": "🛡️",
            "text": "Checking for plagiarism patterns and anomalies…",
            "phase": "anomaly_check",
        })

        # ── Similarity Sentinel: inline plagiarism check ──────────
        sentinel_report = {"sentinel_triggered": False, "max_similarity_score": 0.0}
        try:
            from similarity_sentinel import check_collusion_risk

            if assessment_id and student_reg_no:
                student_id = student_reg_no  # Use reg_no as identifier
                # Extract text from pass1 for comparison
                answer_text = pass1_result.get("justification_note", "") or ""
                # Also use detected key terms as signal
                key_terms_str = ", ".join(pass1_result.get("detected_key_terms", []))
                sentinel_query = f"{answer_text} {key_terms_str}".strip()

                if sentinel_query:
                    collusion = await check_collusion_risk(
                        current_student_id=student_id,
                        answer_text=sentinel_query,
                        assessment_id=assessment_id,
                        threshold=0.92,
                    )

                    if collusion.get("is_flagged"):
                        matches = collusion.get("potential_collusion_with", [])
                        top_match = matches[0] if matches else {}
                        max_score = top_match.get("similarity_score", 0.0)
                        sentinel_report = {
                            "sentinel_triggered": True,
                            "max_similarity_score": max_score,
                            "matches": len(matches),
                            "top_peer": top_match.get("peer_reg_no", "unknown"),
                        }
                        yield _sse_event("step", {
                            "icon": "🚨",
                            "text": f"SENTINEL TRIGGERED: {max_score}% match with {top_match.get('peer_reg_no', 'peer')} — plagiarism risk detected!",
                            "phase": "sentinel_alert",
                        })
                    else:
                        yield _sse_event("step", {
                            "icon": "✅",
                            "text": "Sentinel clear — no plagiarism patterns detected.",
                            "phase": "sentinel_clear",
                        })

                    yield _sse_event("sentinel", sentinel_report)
        except Exception as sent_exc:
            yield _sse_event("step", {
                "icon": "⚠️",
                "text": f"Sentinel check skipped: {str(sent_exc)[:60]}",
                "phase": "sentinel_skip",
            })

        await asyncio.sleep(0.05)

        # ── Step 5: Finalise ──────────────────────────────────────
        # ── DETERMINISTIC MATH: Recalculate final score from per-question
        #    scores using Python, ignoring the LLM's self-reported total.
        final_pq = pass1_result.get("per_question_scores", {})
        if final_pq and isinstance(final_pq, dict):
            deterministic_score = round(sum(
                float(v) for v in final_pq.values() if isinstance(v, (int, float))
            ), 2)
        else:
            # Fallback: use audit score if no per-question breakdown
            deterministic_score = pass2_result["score"]

        # Derive confidence_score from pass2 confidence if not already set
        confidence_score = pass1_result.get("confidence_score", round(pass2_result["confidence"] * 100))
        human_review_required = pass1_result.get("human_review_required", confidence_score < 80)

        final_result = {
            "score": deterministic_score,
            "confidence": pass2_result["confidence"],
            "confidence_score": confidence_score,
            "human_review_required": human_review_required,
            "sentinel_triggered": sentinel_report.get("sentinel_triggered", False),
            "max_similarity_score": sentinel_report.get("max_similarity_score", 0.0),
            "feedback": pass2_result["feedback"],
            "is_flagged": pass2_result["is_flagged"],
            "audit_notes": audit_notes,
            "pass1_score": pass1_result["score"],
            "pass2_score": pass2_result["score"],
            "deterministic_score": deterministic_score,
            "self_corrected": score_changed,
            "diagram_analysis": diagram_result,
            "registration_number": pass1_result.get("registration_number", student_reg_no or "FLAG_FOR_MANUAL"),
            "per_question_scores": final_pq,
            "penalties_applied": pass1_result.get("penalties_applied", []),
            "justification_note": pass1_result.get("justification_note", ""),
        }

        confidence_pct = round(pass2_result["confidence"] * 100, 1)
        yield _sse_event("step", {
            "icon": "💯",
            "text": f"Finalising score with {confidence_pct}% Confidence.",
            "phase": "finalise",
        })

        yield _sse_event("result", final_result)

        # ── Post-Process: Semantic Gap Analysis Sync ──────────────
        #   Update the class-wide Knowledge Map incrementally.
        #   Runs after result is emitted so the UI stays fast.
        if assessment_id:
            yield _sse_event("step", {
                "icon": "🧠",
                "text": "Syncing feedback to Class Knowledge Map…",
                "phase": "gap_sync",
            })
            try:
                from gap_analysis import update_semantic_gap_data

                sb = get_evaluator_supabase()
                if sb:
                    await update_semantic_gap_data(
                        assessment_id=assessment_id,
                        feedback=final_result.get("feedback", []),
                        score=final_result.get("score", 0),
                        diagram_analysis=diagram_result,
                        supabase_client=sb,
                    )
                    yield _sse_event("step", {
                        "icon": "✅",
                        "text": "Knowledge Map updated — gap analysis data synced.",
                        "phase": "gap_sync_done",
                    })
                else:
                    yield _sse_event("step", {
                        "icon": "⚠️",
                        "text": "Gap sync skipped — database not available.",
                        "phase": "gap_sync_skip",
                    })
            except Exception as gap_exc:
                yield _sse_event("step", {
                    "icon": "⚠️",
                    "text": f"Gap sync skipped: {str(gap_exc)[:80]}",
                    "phase": "gap_sync_error",
                })

        yield _sse_event("done", {"status": "complete"})

    except QuotaExhaustedError as qe:
        yield _sse_event("error", {
            "message": f"⚠️ API quota exhausted after retries. Please wait {int(qe.wait_seconds)}s and try again.",
            "status": "QUOTA_EXHAUSTED",
        })
        yield _sse_event("done", {"status": "error"})

    except Exception as exc:
        err_msg = str(exc)
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            yield _sse_event("error", {
                "message": "⚠️ API quota exhausted. Please wait 60 seconds and try again.",
                "status": "QUOTA_EXHAUSTED",
            })
        else:
            yield _sse_event("error", {"message": err_msg})
        yield _sse_event("done", {"status": "error"})


# ---------------------------------------------------------------------------
#  Standalone Quick-Test (run directly: python evaluator.py <image_path>)
# ---------------------------------------------------------------------------

async def _quick_evaluate(image_path: str):
    """Run the full agentic pipeline on a single image and print the result."""
    import sys
    from pathlib import Path

    path = Path(image_path)
    if not path.exists():
        print(f"❌ File not found: {image_path}")
        sys.exit(1)

    image_bytes = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"

    print(f"📄 Loading: {path.name}")
    print("🚀 Starting AuraGrade Agentic Evaluation Engine…\n")

    final = None
    async for event_str in agentic_grade_stream(image_bytes, mime_type=mime):
        # Print step events to console for visibility
        if event_str.startswith("event: step"):
            data_line = event_str.split("data: ", 1)[1].split("\n")[0]
            step = json.loads(data_line)
            print(f"  {step.get('icon', '▸')} {step.get('text', '')}")
        elif event_str.startswith("event: result"):
            data_line = event_str.split("data: ", 1)[1].split("\n")[0]
            final = json.loads(data_line)

    if final:
        print("\n" + "=" * 50)
        print("🎓 AURAGRADE EVALUATION REPORT")
        print("=" * 50)
        print(json.dumps(final, indent=4))
    else:
        print("\n❌ No result produced — check API key and image.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <path_to_answer_script_image>")
        print("Example: python evaluator.py 1000214286.jpg")
        sys.exit(1)

    asyncio.run(_quick_evaluate(sys.argv[1]))
