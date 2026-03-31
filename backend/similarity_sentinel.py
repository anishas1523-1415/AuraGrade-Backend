"""
similarity_sentinel.py — Cross-Script Collusion Detection (Semantic Similarity)

Uses Pinecone's integrated embedding (llama-text-embed-v2) to store a
compact fingerprint of every graded script.  When a new script arrives,
we query the same namespace for suspiciously close neighbours.

Namespace: "sentinel"  (separate from the RAG model-answer namespace)

Vector metadata stored per record:
  - student_id   : UUID
  - assessment_id : UUID
  - reg_no       : student register number
  - text_preview : first 200 chars of the answer (for dashboard display)
  - graded_at    : ISO timestamp
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
#  Pinecone index — reuses the same lazy-init pattern from evaluator.py
# ---------------------------------------------------------------------------

_pinecone_index = None

SENTINEL_NAMESPACE = "sentinel"


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
        print(f"⚠️  Sentinel: Pinecone init failed: {exc}")
        return None


# ---------------------------------------------------------------------------
#  Upsert a student submission into the sentinel namespace
# ---------------------------------------------------------------------------


async def index_student_submission(
    grade_id: str,
    student_id: str,
    assessment_id: str,
    reg_no: str,
    answer_text: str,
    graded_at: str | None = None,
) -> bool:
    """
    Store the full answer text in the sentinel namespace so future
    submissions can be compared against it.
    Returns True if upserted, False if Pinecone is unavailable.
    """
    index = _get_pinecone_index()
    if index is None:
        return False

    preview = answer_text[:200].replace("\n", " ").strip()

    record = {
        "_id": f"sentinel_{grade_id}",
        "text": answer_text,                 # Pinecone auto-embeds this
        "student_id": student_id,
        "assessment_id": assessment_id,
        "reg_no": reg_no,
        "text_preview": preview,
        "graded_at": graded_at or datetime.now(timezone.utc).isoformat(),
    }

    try:
        index.upsert_records(namespace=SENTINEL_NAMESPACE, records=[record])
        return True
    except Exception as exc:
        print(f"⚠️  Sentinel upsert failed: {exc}")
        return False


# ---------------------------------------------------------------------------
#  Check collusion risk for a submission
# ---------------------------------------------------------------------------


async def check_collusion_risk(
    current_student_id: str,
    answer_text: str,
    assessment_id: str,
    threshold: float = 0.92,
    top_k: int = 5,
) -> dict:
    """
    Query the sentinel namespace for semantically similar answers
    within the SAME assessment.  Returns a collusion report.

    Returns:
    {
      "is_flagged": bool,
      "potential_collusion_with": [
        {
          "peer_id": str,
          "peer_reg_no": str,
          "similarity_score": float,    # 0-100
          "matched_content_snippet": str,
          "status": "Critical" | "Warning"
        }
      ]
    }
    """
    index = _get_pinecone_index()
    if index is None:
        return {"is_flagged": False, "potential_collusion_with": [], "error": "Pinecone not configured"}

    try:
        results = index.search(
            namespace=SENTINEL_NAMESPACE,
            query={
                "top_k": top_k,
                "inputs": {"text": answer_text},
                "filter": {"assessment_id": {"$eq": assessment_id}},
            },
            fields=["student_id", "reg_no", "text_preview", "assessment_id", "graded_at"],
        )

        matches = []
        for hit in results.get("result", {}).get("hits", []):
            fields = hit.get("fields", {})
            # Skip self-match
            if fields.get("student_id") == current_student_id:
                continue

            score = hit.get("_score", 0)
            if score >= threshold:
                pct = round(score * 100, 2)
                matches.append({
                    "peer_id": fields.get("student_id", "unknown"),
                    "peer_reg_no": fields.get("reg_no", "—"),
                    "similarity_score": pct,
                    "matched_content_snippet": fields.get("text_preview", "")[:150],
                    "graded_at": fields.get("graded_at"),
                    "status": "Critical" if pct >= 95 else "Warning",
                })

        # Sort by similarity descending
        matches.sort(key=lambda m: m["similarity_score"], reverse=True)

        return {
            "is_flagged": len(matches) > 0,
            "potential_collusion_with": matches,
        }

    except Exception as exc:
        print(f"⚠️  Sentinel query failed: {exc}")
        return {"is_flagged": False, "potential_collusion_with": [], "error": str(exc)}


# ---------------------------------------------------------------------------
#  Batch scan: check all graded submissions for an assessment
# ---------------------------------------------------------------------------


async def scan_assessment_collusion(
    assessment_id: str,
    supabase_client,
    threshold: float = 0.90,
) -> dict:
    """
    Pull all grades for an assessment from Supabase, then cross-check
    each against the sentinel index.  Returns a full collusion report.
    """
    if not supabase_client:
        return {"flags": [], "total_checked": 0, "error": "Database not configured"}

    # Fetch all grades with student info for this assessment
    result = (
        supabase_client.table("grades")
        .select("id, student_id, ai_score, feedback, graded_at, students(reg_no, name)")
        .eq("assessment_id", assessment_id)
        .order("graded_at", desc=False)
        .execute()
    )

    grades = result.data or []
    if len(grades) < 2:
        return {"flags": [], "total_checked": len(grades), "message": "Need at least 2 submissions to compare"}

    all_flags = []
    seen_pairs: set[tuple[str, str]] = set()

    for grade in grades:
        # Build the answer text from feedback (the textual content graded)
        feedback = grade.get("feedback", [])
        if isinstance(feedback, list):
            answer_text = " ".join(str(f) for f in feedback)
        elif isinstance(feedback, str):
            answer_text = feedback
        else:
            answer_text = str(feedback)

        if len(answer_text) < 20:
            continue  # Skip too-short submissions

        student_id = grade["student_id"]
        student_info = grade.get("students", {})
        reg_no = student_info.get("reg_no", "—") if isinstance(student_info, dict) else "—"

        report = await check_collusion_risk(
            current_student_id=student_id,
            answer_text=answer_text,
            assessment_id=assessment_id,
            threshold=threshold,
        )

        for match in report.get("potential_collusion_with", []):
            # Deduplicate: A↔B same as B↔A
            pair = tuple(sorted([student_id, match["peer_id"]]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            all_flags.append({
                "studentA": reg_no,
                "studentA_id": student_id,
                "studentB": match["peer_reg_no"],
                "studentB_id": match["peer_id"],
                "similarity": match["similarity_score"],
                "status": match["status"],
                "snippet_a": answer_text[:150],
                "snippet_b": match["matched_content_snippet"],
                "graded_at": grade.get("graded_at"),
            })

    # Sort by severity
    all_flags.sort(key=lambda f: f["similarity"], reverse=True)

    return {
        "flags": all_flags,
        "total_checked": len(grades),
        "assessment_id": assessment_id,
    }
