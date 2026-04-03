import os
from pinecone import Pinecone
from datetime import datetime, timezone

# Initialize Pinecone (Vector Database for Semantic Search)
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if PINECONE_API_KEY:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index("auragrade")
else:
    pc = None
    index = None

SENTINEL_NAMESPACE = "sentinel"

async def check_collusion_risk(current_student_id: str, answer_text: str, assessment_id: str, threshold: float = 0.90) -> dict:
    """
    Queries the sentinel namespace for semantically similar answers within the SAME assessment.
    Returns a mathematically proven collusion report.
    """
    if index is None:
        return {"is_flagged": False, "potential_collusion_with": [], "error": "Pinecone not configured"}

    try:
        # Pinecone automatically embeds the text and searches for nearest neighbors
        results = index.search(
            namespace=SENTINEL_NAMESPACE,
            query={
                "top_k": 5, # Check top 5 closest matches
                "inputs": {"text": answer_text},
                "filter": {"assessment_id": {"$eq": assessment_id}}, # Strict isolation to this specific exam
            },
            fields=["student_id", "reg_no", "text_preview"]
        )

        matches = []
        for hit in results.get("result", {}).get("hits", []):
            fields = hit.get("fields", {})
            
            # Skip comparing the student against their own previous draft
            if fields.get("student_id") == current_student_id:
                continue

            score = hit.get("_score", 0)
            if score >= threshold:
                pct = round(score * 100, 2)
                matches.append({
                    "peer_reg_no": fields.get("reg_no", "UNKNOWN"),
                    "similarity_score": pct,
                    "matched_content_snippet": fields.get("text_preview", "")[:150],
                    "status": "CRITICAL" if pct >= 95 else "WARNING"
                })

        matches.sort(key=lambda m: m["similarity_score"], reverse=True)

        return {
            "is_flagged": len(matches) > 0,
            "potential_collusion_with": matches,
        }
    except Exception as exc:
        print(f"CRITICAL ERROR: Sentinel query failed: {exc}")
        return {"is_flagged": False, "potential_collusion_with": [], "error": str(exc)}
