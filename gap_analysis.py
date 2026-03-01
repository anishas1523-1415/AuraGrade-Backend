"""
AuraGrade — Semantic Gap Analysis Engine (Knowledge Mapping)
=============================================================
Analyzes all student grades for a specific assessment to uncover
class-wide **Knowledge Gaps** and **Strengths** using Gemini reasoning.

This transforms AuraGrade from a grading tool into a
**Pedagogical Intelligence System**:
  - Identifies the top concepts students consistently struggled with
  - Highlights collective strengths across the cohort
  - Generates an actionable remediation plan for the professor
  - Returns per-concept proficiency scores for Radar Chart visualization

Architecture:
  1. Fetch all feedback + scores for an assessment from Supabase
  2. Feed aggregated data into Gemini for semantic analysis
  3. Return structured JSON: gaps, strengths, concept proficiency map, remediation

Publication value:
  - Demonstrates "Pedagogical Intelligence" beyond simple grading
  - Provides Explainable AI (XAI) insights for institutional use
  - Enables data-driven curriculum improvement at scale
"""

from __future__ import annotations

import json
import os
from typing import Optional

from google import genai
from google.genai import types
from supabase import Client


# ---------------------------------------------------------------------------
#  Gemini client (shared with main.py)
# ---------------------------------------------------------------------------

_gemini_client: genai.Client | None = None


def get_gap_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _gemini_client


def set_gap_client(client: genai.Client):
    """Allow main.py to inject the shared Gemini client."""
    global _gemini_client
    _gemini_client = client


# ---------------------------------------------------------------------------
#  Core — Class Knowledge Map Generator
# ---------------------------------------------------------------------------

async def generate_class_knowledge_map(
    assessment_id: str,
    supabase_client: Client,
) -> dict:
    """
    Analyzes all student grades for a specific exam to produce a
    class-wide 'Knowledge Map' — identifying gaps, strengths,
    concept-level proficiency, and a remediation plan.

    Parameters
    ----------
    assessment_id : str
        UUID of the assessment to analyze.
    supabase_client : Client
        Active Supabase client instance.

    Returns
    -------
    dict with keys:
        gaps          : list[dict]  — top concepts students failed
        strengths     : list[dict]  — top concepts students mastered
        proficiency   : list[dict]  — per-concept radar chart data
        remediation   : str         — actionable remediation plan
        summary       : str         — one-line executive summary
        total_scripts : int         — number of scripts analyzed
        avg_score     : float       — mean score for context
    """

    client = get_gap_client()

    # 1. Fetch all grades for this assessment
    grades_response = (
        supabase_client.table("grades")
        .select("ai_score, confidence, feedback, is_flagged, students(reg_no, name)")
        .eq("assessment_id", assessment_id)
        .execute()
    )

    grades_data = grades_response.data or []
    total_scripts = len(grades_data)

    if total_scripts == 0:
        return {
            "gaps": [],
            "strengths": [],
            "proficiency": [],
            "remediation": "No graded scripts found for this assessment.",
            "summary": "Insufficient data for analysis.",
            "total_scripts": 0,
            "avg_score": 0.0,
        }

    # 2. Fetch assessment rubric for context
    assessment_response = (
        supabase_client.table("assessments")
        .select("subject, title, rubric_json, model_answer")
        .eq("id", assessment_id)
        .single()
        .execute()
    )

    assessment = assessment_response.data or {}
    rubric = assessment.get("rubric_json") or {}
    subject = assessment.get("subject", "Unknown Subject")
    title = assessment.get("title", "Unknown Assessment")

    # 3. Calculate basic stats
    scores = [g.get("ai_score", 0) for g in grades_data]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

    # 4. Aggregate all feedback into a single analysis payload
    all_feedback = []
    for g in grades_data:
        fb = g.get("feedback", [])
        student_info = g.get("students", {})
        student_name = student_info.get("name", "Unknown") if student_info else "Unknown"
        score = g.get("ai_score", 0)
        all_feedback.append({
            "student": student_name,
            "score": score,
            "feedback": fb if isinstance(fb, list) else [str(fb)],
            "flagged": g.get("is_flagged", False),
        })

    # 5. Build the Gemini analysis prompt
    rubric_text = json.dumps(rubric, indent=2) if rubric else "No rubric defined."

    analysis_prompt = f"""You are a Pedagogical Intelligence System analyzing the collective
performance of {total_scripts} students on an examination.

## Context
- **Subject**: {subject}
- **Assessment**: {title}
- **Average Score**: {avg_score}/10
- **Total Scripts Analyzed**: {total_scripts}

## Rubric Used for Grading
{rubric_text}

## Aggregated Student Performance Data
{json.dumps(all_feedback, indent=2)}

## Your Analysis Mandate

Perform a deep semantic analysis of ALL the feedback across all students.
Identify PATTERNS — not individual issues.

### 1. Knowledge Gaps (Top 3-5)
For each gap, identify:
- The specific **concept** or **sub-topic** students struggled with
- A brief explanation of WHY (common misconceptions, formula errors, diagram mistakes)
- What percentage of students exhibited this gap
- Severity: "Critical" (>60% affected), "Moderate" (30-60%), or "Minor" (<30%)

### 2. Strengths (Top 3-5)
Concepts the class collectively demonstrated mastery of.

### 3. Concept Proficiency Map
Generate a list of 6-8 key concepts/topics from the rubric/assessment.
For each, assign a proficiency score (0-100) representing the class average.
This will power a Radar Chart visualization.

### 4. Remediation Plan
A 3-5 sentence actionable plan for the professor — what to re-teach, 
which pedagogical approach to use, and which resources might help.

## Output Format (strict JSON)
{{
    "gaps": [
        {{
            "concept": "string — the specific sub-topic",
            "reason": "string — why students struggled",
            "affected_pct": <int 0-100>,
            "severity": "Critical | Moderate | Minor",
            "example_mistake": "string — a representative error from the data"
        }}
    ],
    "strengths": [
        {{
            "concept": "string — the sub-topic",
            "mastery_pct": <int 0-100>,
            "evidence": "string — what students did well"
        }}
    ],
    "proficiency": [
        {{
            "concept": "string — topic name for radar chart label",
            "value": <int 0-100 — class proficiency percentage>
        }}
    ],
    "remediation": "string — actionable multi-sentence plan",
    "summary": "string — one-line executive summary of class performance"
}}
"""

    # 6. Call Gemini for semantic analysis
    from gemini_retry import call_gemini, parse_response
    response = call_gemini(
        client,
        model="gemini-3-flash-preview",
        contents=[analysis_prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,  # Deterministic analysis
        ),
    )

    result = parse_response(response)

    # Safety net
    if not result or not isinstance(result, dict):
        result = {
            "gaps": [],
            "strengths": [],
            "proficiency": [],
            "remediation": "Analysis could not be completed — insufficient data or model error.",
            "summary": "Analysis failed.",
        }

    # Ensure all keys exist
    result.setdefault("gaps", [])
    result.setdefault("strengths", [])
    result.setdefault("proficiency", [])
    result.setdefault("remediation", "No remediation plan generated.")
    result.setdefault("summary", "Analysis complete.")

    # Inject metadata
    result["total_scripts"] = total_scripts
    result["avg_score"] = avg_score
    result["subject"] = subject
    result["title"] = title

    return result


# ---------------------------------------------------------------------------
#  Incremental Gap Sync — called after every grading to update cache
# ---------------------------------------------------------------------------

async def update_semantic_gap_data(
    assessment_id: str,
    feedback: list,
    score: float,
    diagram_analysis: dict | None,
    supabase_client: Client,
) -> None:
    """
    Lightweight post-grading hook called from the evaluator pipeline.

    Stores each grade's feedback into a `gap_analysis_cache` table so that
    the full `generate_class_knowledge_map` call (triggered by the admin)
    can also leverage pre-aggregated insights.

    If the cache table doesn't exist, gracefully falls back to a simple
    counter bump on the assessments metadata.

    This ensures the Knowledge Map stays "warm" and up-to-date without
    running the expensive full Gemini analysis after every single paper.
    """

    try:
        # 1. Build the cache entry
        cache_entry = {
            "assessment_id": assessment_id,
            "score": score,
            "feedback_json": json.dumps(feedback) if isinstance(feedback, list) else str(feedback),
            "has_diagram": bool(diagram_analysis),
        }

        if diagram_analysis:
            cache_entry["diagram_type"] = diagram_analysis.get("diagram_type", "none")
            cache_entry["diagram_score"] = diagram_analysis.get("logic_score", 0)
            cache_entry["diagram_valid"] = diagram_analysis.get("is_valid", False)

        # 2. Try inserting into gap_analysis_cache table
        #    This table may not exist — that's fine, we degrade gracefully.
        try:
            supabase_client.table("gap_analysis_cache").insert(cache_entry).execute()
        except Exception:
            # Table doesn't exist yet — fall back to assessments metadata update
            pass

        # 3. Bump the graded_count on the assessment for tracking
        try:
            current = (
                supabase_client.table("assessments")
                .select("id")
                .eq("id", assessment_id)
                .single()
                .execute()
            )
            if current.data:
                supabase_client.rpc(
                    "increment_gap_counter",
                    {"row_id": assessment_id}
                ).execute()
        except Exception:
            # RPC may not exist — not critical
            pass

    except Exception as exc:
        # Never crash the grading pipeline over a cache update
        print(f"⚠️  Gap analysis cache update failed (non-fatal): {exc}")


# ---------------------------------------------------------------------------
#  Formatted Knowledge Map — returns Recharts-ready + remediation structure
# ---------------------------------------------------------------------------

async def generate_formatted_knowledge_map(
    assessment_id: str,
    supabase_client: Client,
) -> dict:
    """
    Wrapper around generate_class_knowledge_map that returns the data
    in the format expected by the admin API:
      - map_data (formatted for Recharts Radar Chart)
      - remediation (the remediation plan)
      - raw (full analysis for the frontend component)
    """

    raw = await generate_class_knowledge_map(assessment_id, supabase_client)

    # Build Recharts-ready radar chart data from proficiency
    formatted_chart_data = []
    for item in raw.get("proficiency", []):
        formatted_chart_data.append({
            "concept": item["concept"],
            "classAvg": item["value"],
            "fullMark": 100,
        })

    return {
        "assessment_id": assessment_id,
        "map_data": formatted_chart_data,
        "remediation": raw.get("remediation", "No data."),
        "raw": raw,
    }


# ---------------------------------------------------------------------------
#  Comparative Analysis — Compare two assessments
# ---------------------------------------------------------------------------

async def compare_assessments(
    assessment_id_1: str,
    assessment_id_2: str,
    supabase_client: Client,
) -> dict:
    """
    Compare knowledge maps between two assessments to track
    improvement or regression across the semester.

    Returns a delta analysis with concepts that improved vs degraded.
    """

    map1 = await generate_class_knowledge_map(assessment_id_1, supabase_client)
    map2 = await generate_class_knowledge_map(assessment_id_2, supabase_client)

    # Build proficiency lookup
    prof1 = {item["concept"]: item["value"] for item in map1.get("proficiency", [])}
    prof2 = {item["concept"]: item["value"] for item in map2.get("proficiency", [])}

    # Compute deltas for overlapping concepts
    all_concepts = set(list(prof1.keys()) + list(prof2.keys()))
    deltas = []
    for concept in all_concepts:
        v1 = prof1.get(concept, 0)
        v2 = prof2.get(concept, 0)
        deltas.append({
            "concept": concept,
            "assessment_1_value": v1,
            "assessment_2_value": v2,
            "delta": v2 - v1,
            "trend": "improved" if v2 > v1 else "degraded" if v2 < v1 else "stable",
        })

    deltas.sort(key=lambda x: x["delta"], reverse=True)

    return {
        "assessment_1": {
            "id": assessment_id_1,
            "subject": map1.get("subject", ""),
            "title": map1.get("title", ""),
            "avg_score": map1.get("avg_score", 0),
        },
        "assessment_2": {
            "id": assessment_id_2,
            "subject": map2.get("subject", ""),
            "title": map2.get("title", ""),
            "avg_score": map2.get("avg_score", 0),
        },
        "deltas": deltas,
        "improved_count": sum(1 for d in deltas if d["trend"] == "improved"),
        "degraded_count": sum(1 for d in deltas if d["trend"] == "degraded"),
    }
