"""
Reindex existing assessment model answers into Pinecone.

Usage:
  python scripts/reindex_pinecone.py

Environment (loaded from backend/.env and backend/.env.local if present):
  SUPABASE_URL
  SUPABASE_KEY
  PINECONE_API_KEY
  PINECONE_INDEX or PINECONE_INDEX_NAME
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

# Make backend modules importable when script is run from project root.
sys.path.insert(0, str(BACKEND_DIR))

from evaluator import upsert_model_answer  # noqa: E402


def _load_env() -> None:
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.local")
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env.local")


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def _run() -> int:
    _load_env()

    supabase_url = _require_env("SUPABASE_URL")
    supabase_key = _require_env("SUPABASE_KEY")
    _require_env("PINECONE_API_KEY")

    client = create_client(supabase_url, supabase_key)

    result = (
        client.table("assessments")
        .select("id, title, model_answer")
        .not_.is_("model_answer", "null")
        .execute()
    )

    rows = result.data or []
    if not rows:
        print("No assessments with model_answer found. Nothing to index.")
        return 0

    total_chunks = 0
    indexed = 0
    skipped = 0

    for row in rows:
        assessment_id = str(row.get("id", "")).strip()
        title = (row.get("title") or "Untitled").strip()
        model_answer = (row.get("model_answer") or "").strip()

        if not assessment_id or not model_answer:
            skipped += 1
            continue

        try:
            chunks = await upsert_model_answer(assessment_id, model_answer)
            total_chunks += int(chunks)
            indexed += 1
            print(f"Indexed assessment '{title}' ({assessment_id}) -> {chunks} chunks")
        except Exception as exc:
            skipped += 1
            print(f"Skipped assessment '{title}' ({assessment_id}): {exc}")

    print("\nReindex complete")
    print(f"Assessments indexed: {indexed}")
    print(f"Assessments skipped: {skipped}")
    print(f"Total chunks upserted: {total_chunks}")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception as exc:
        print(f"Reindex failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
