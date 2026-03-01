"""
AuraGrade — Diagram-to-Code Validation Agent (Vision Logic)
=============================================================
The "Novelty" feature: Converts handwritten diagrams (Neural Networks,
Flowcharts, Circuit Diagrams, ER Diagrams, etc.) into **Mermaid.js code**
and validates the structural & logical correctness.

This is the key differentiator for SIH / Cisco Ideathon submissions:
  - Most OCR/grading projects cannot "understand" diagrams
  - AuraGrade converts them to executable graph code
  - Then validates the logic at a code-level, not pixel-level

Pipeline:
  1. Gemini Vision extracts the diagram from the answer sheet
  2. Converts to Mermaid.js syntax (renderable graph code)
  3. Validates logical correctness:
     - Flowcharts: checks for unreachable nodes, missing terminators
     - Neural Networks: validates layer connectivity, dimension flow
     - ER Diagrams: checks cardinality, missing relationships
     - General: structural completeness
  4. Returns structured analysis with mermaid code, validity, and flaws

Publication value:
  - Demonstrates "Visual Reasoning" beyond OCR
  - Novel IP: diagram-to-code multimodal pipeline
  - Reduces AI hallucination on visual grading tasks
  - Provides XAI output (the mermaid code IS the explanation)
"""

from __future__ import annotations

import json
import os
import asyncio
from typing import AsyncGenerator, Optional

from google import genai
from google.genai import types

from evaluator import _sse_event


# ---------------------------------------------------------------------------
#  Gemini client (shared with main.py)
# ---------------------------------------------------------------------------

_gemini_client: genai.Client | None = None


def get_vision_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _gemini_client


def set_vision_client(client: genai.Client):
    """Allow main.py to inject the shared Gemini client."""
    global _gemini_client
    _gemini_client = client


# ---------------------------------------------------------------------------
#  Core — Diagram Detection & Classification
# ---------------------------------------------------------------------------

DIAGRAM_DETECT_PROMPT = """You are a Diagram Detection Agent for a university exam grading system.

Analyze this handwritten answer sheet image and determine:
1. Does it contain any diagrams, flowcharts, circuit diagrams, ER diagrams,
   neural network architectures, state machines, or similar visual structures?
2. What TYPE of diagram(s) are present?
3. Where in the image are they located (approximate region)?

Output strictly in JSON:
{
    "has_diagram": <boolean — true if any diagram is detected>,
    "diagram_count": <int — how many distinct diagrams>,
    "diagrams": [
        {
            "type": "flowchart | neural_network | er_diagram | circuit | state_machine | tree | graph | uml | other",
            "description": "brief description of what the diagram shows",
            "region": "top | middle | bottom | left | right | full"
        }
    ],
    "confidence": "HIGH | MEDIUM | LOW"
}
"""


async def detect_diagrams(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Detect whether an answer sheet contains diagrams and classify them.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data.
    mime_type : str
        MIME type of the image.

    Returns
    -------
    dict with diagram detection results.
    """
    client = get_vision_client()

    from gemini_retry import call_gemini_async, parse_response
    response = await call_gemini_async(
        client,
        model="gemini-3-flash-preview",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            DIAGRAM_DETECT_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    result = parse_response(response)

    if not result or not isinstance(result, dict):
        return {
            "has_diagram": False,
            "diagram_count": 0,
            "diagrams": [],
            "confidence": "LOW",
        }

    result.setdefault("has_diagram", False)
    result.setdefault("diagram_count", 0)
    result.setdefault("diagrams", [])
    result.setdefault("confidence", "MEDIUM")

    return result


# ---------------------------------------------------------------------------
#  Core — Diagram-to-Code Conversion + Validation
# ---------------------------------------------------------------------------

DIAGRAM_TO_CODE_PROMPT = """You are a Diagram-to-Code Validation Agent — a novel AI system that
converts handwritten diagrams into formal graph code and validates their logic.

## Task
1. **Extract** the handwritten diagram from this answer sheet image.
2. **Convert** the diagram to **Mermaid.js** code (the standard graph description language).
3. **Validate** the logic and structure of the diagram.

## Diagram-Type-Specific Validation Rules

### Flowcharts
- Must have START and END nodes (terminators)
- No orphan/unreachable nodes
- Decision nodes (diamonds) must have Yes/No or True/False branches
- All branches must eventually converge or terminate
- Check for infinite loops without exit conditions

### Neural Network Architectures
- Layer dimensions must be mathematically compatible
  (output of layer N must match input of layer N+1)
- Activation functions should be appropriate for the layer type
- Check for missing bias terms if relevant
- Validate if the architecture matches the stated task (classification → softmax, etc.)

### ER Diagrams
- Check cardinality notation (1:1, 1:N, M:N)
- All entities should have primary keys
- Relationships should connect valid entities
- No dangling relationships

### State Machines / Automata
- Must have an initial state
- Should have at least one accepting/final state
- All transitions must be labeled
- Check for non-determinism if it should be deterministic (DFA vs NFA)

### General (Trees, Graphs, UML)
- Structural completeness
- Label consistency
- Edge direction validity

## Mermaid.js Code Standards
- Use proper Mermaid syntax: graph TD, flowchart LR, stateDiagram-v2, erDiagram, etc.
- Include meaningful node labels
- Preserve the student's intended structure as faithfully as possible

## Output Format (strict JSON)
{
    "diagram_type": "flowchart | neural_network | er_diagram | circuit | state_machine | tree | graph | uml | other",
    "mermaid_code": "string — valid Mermaid.js code representing the diagram",
    "is_valid": <boolean — true if the diagram logic is correct>,
    "logic_score": <float 0-10 — how logically sound the diagram is>,
    "logic_flaws": [
        {
            "flaw": "string — description of the logical flaw",
            "severity": "critical | major | minor",
            "suggestion": "string — how to fix it"
        }
    ],
    "structural_notes": "string — brief assessment of structural clarity and completeness",
    "student_intent": "string — what the student was TRYING to show with this diagram"
}
"""


async def validate_diagram_logic(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Converts a handwritten diagram to Mermaid.js code and validates
    its structural and logical correctness.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data containing the diagram.
    mime_type : str
        MIME type of the image.

    Returns
    -------
    dict with keys:
        diagram_type     : str
        mermaid_code     : str
        is_valid         : bool
        logic_score      : float
        logic_flaws      : list[dict]
        structural_notes : str
        student_intent   : str
    """
    client = get_vision_client()

    from gemini_retry import call_gemini_async, parse_response
    response = await call_gemini_async(
        client,
        model="gemini-3-flash-preview",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            DIAGRAM_TO_CODE_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        ),
    )

    result = parse_response(response)

    # Safety net
    if not result or not isinstance(result, dict):
        return {
            "diagram_type": "unknown",
            "mermaid_code": "",
            "is_valid": False,
            "logic_score": 0.0,
            "logic_flaws": [
                {
                    "flaw": "Could not extract or parse diagram from image",
                    "severity": "critical",
                    "suggestion": "Ensure the diagram is clearly drawn with visible labels",
                }
            ],
            "structural_notes": "Diagram extraction failed.",
            "student_intent": "Unknown",
        }

    # Ensure all required keys
    result.setdefault("diagram_type", "unknown")
    result.setdefault("mermaid_code", "")
    result.setdefault("is_valid", False)
    result.setdefault("logic_score", 0.0)
    result.setdefault("logic_flaws", [])
    result.setdefault("structural_notes", "")
    result.setdefault("student_intent", "")

    return result


# ---------------------------------------------------------------------------
#  SSE Streaming — Diagram Validation Pipeline
# ---------------------------------------------------------------------------

async def diagram_validation_stream(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> AsyncGenerator[str, None]:
    """
    Full diagram validation pipeline streamed as SSE events.
    Integrates into the grading SSE stream as additional steps.

    Events emitted:
        step            : reasoning step updates
        diagram_detect  : detection results
        diagram_result  : full validation results with mermaid code
        done            : completion signal
        error           : any errors
    """

    try:
        # ── Step 1: Detecting diagrams ────────────────────────────
        yield _sse_event("step", {
            "icon": "📐",
            "text": "Diagram Detection Agent scanning for visual structures…",
            "phase": "diagram_detect",
        })
        await asyncio.sleep(0.3)

        detection = await detect_diagrams(image_bytes, mime_type)

        yield _sse_event("diagram_detect", detection)

        if not detection.get("has_diagram"):
            yield _sse_event("step", {
                "icon": "📝",
                "text": "No diagrams detected — script is text-only.",
                "phase": "diagram_skip",
            })
            yield _sse_event("diagram_result", {
                "has_diagram": False,
                "diagram_type": None,
                "mermaid_code": None,
                "is_valid": None,
                "logic_score": None,
                "logic_flaws": [],
                "skipped": True,
            })
            yield _sse_event("done", {"status": "complete"})
            return

        diagrams = detection.get("diagrams", [])
        diagram_count = len(diagrams)
        diagram_types = ", ".join(d.get("type", "unknown") for d in diagrams)

        yield _sse_event("step", {
            "icon": "🔍",
            "text": f"Detected {diagram_count} diagram(s): {diagram_types}",
            "phase": "diagram_found",
        })
        await asyncio.sleep(0.2)

        # ── Step 2: Convert to Mermaid.js code ────────────────────
        yield _sse_event("step", {
            "icon": "💻",
            "text": "Converting handwritten diagram to Mermaid.js code…",
            "phase": "diagram_convert",
        })
        await asyncio.sleep(0.3)

        validation = await validate_diagram_logic(image_bytes, mime_type)

        yield _sse_event("step", {
            "icon": "🔗",
            "text": f"Generated Mermaid code for {validation.get('diagram_type', 'unknown')} diagram.",
            "phase": "diagram_code_done",
        })
        await asyncio.sleep(0.2)

        # ── Step 3: Logic validation ──────────────────────────────
        yield _sse_event("step", {
            "icon": "⚙️",
            "text": "Running logic validation engine…",
            "phase": "diagram_validate",
        })
        await asyncio.sleep(0.2)

        logic_flaws = validation.get("logic_flaws", [])
        is_valid = validation.get("is_valid", False)
        logic_score = validation.get("logic_score", 0.0)

        if is_valid:
            yield _sse_event("step", {
                "icon": "✅",
                "text": f"Diagram logic validated — score: {logic_score}/10 (no structural flaws)",
                "phase": "diagram_valid",
            })
        else:
            flaw_count = len(logic_flaws)
            critical_count = sum(1 for f in logic_flaws if f.get("severity") == "critical")
            yield _sse_event("step", {
                "icon": "⚠️",
                "text": f"Found {flaw_count} logic flaw(s) ({critical_count} critical) — score: {logic_score}/10",
                "phase": "diagram_flaws",
            })

            # Emit each flaw as a sub-step
            for flaw in logic_flaws[:5]:  # Cap at 5 for UI
                severity_icon = "🔴" if flaw.get("severity") == "critical" else "🟡" if flaw.get("severity") == "major" else "🟢"
                yield _sse_event("step", {
                    "icon": severity_icon,
                    "text": f"[{flaw.get('severity', 'unknown').upper()}] {flaw.get('flaw', '')}",
                    "phase": "diagram_flaw_detail",
                })

        # ── Step 4: Emit full result ──────────────────────────────
        yield _sse_event("diagram_result", {
            "has_diagram": True,
            **validation,
        })

        yield _sse_event("done", {"status": "complete"})

    except Exception as exc:
        yield _sse_event("error", {"message": f"Diagram validation failed: {str(exc)}"})
        yield _sse_event("done", {"status": "error"})
