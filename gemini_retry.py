"""
AuraGrade — Gemini API Retry Wrapper with Key Rotation
=========================================================
Centralised retry logic with exponential backoff AND automatic
API-key failover for all Gemini API calls.

Handles 429 RESOURCE_EXHAUSTED (rate-limit) and transient 5xx server errors
automatically so the grading pipeline never crashes on quota limits.
When one key is exhausted, the next key in the pool is tried.
"""

from __future__ import annotations

import json
import os
import asyncio
import functools
import threading
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

logger = logging.getLogger("auragrade.retry")

# ---------------------------------------------------------------------------
#  API Key Pool — automatic failover across multiple Gemini keys
# ---------------------------------------------------------------------------

_key_pool: list[str] = []
_key_index: int = 0
_key_lock = threading.Lock()


def init_key_pool():
    """Build the key pool from environment variables on startup."""
    global _key_pool
    keys = []
    primary = os.environ.get("GEMINI_API_KEY", "")
    if primary:
        keys.append(primary)
    # Support GEMINI_API_KEY_2, _3, etc.
    for i in range(2, 10):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "")
        if k:
            keys.append(k)
    _key_pool = keys
    if len(keys) > 1:
        print(f"✅ Gemini key pool: {len(keys)} keys loaded (failover enabled)")
    elif len(keys) == 1:
        print("✅ Gemini key pool: 1 key loaded")
    else:
        print("⚠️  No GEMINI_API_KEY found in environment")


def _rotate_client():
    """Get a fresh genai.Client using the next key in the pool."""
    global _key_index
    if not _key_pool:
        return None
    with _key_lock:
        key = _key_pool[_key_index % len(_key_pool)]
        _key_index = (_key_index + 1) % len(_key_pool)
    return genai.Client(api_key=key)

# Retry on ClientError (429 rate-limit) and ServerError (5xx transient)
_RETRYABLE = (genai_errors.ClientError, genai_errors.ServerError)


def _should_retry(exc: BaseException) -> bool:
    """Only retry on rate-limit (429) or transient server errors."""
    if isinstance(exc, genai_errors.ClientError):
        # ClientError includes 429, 400, etc.  Always retry — the
        # most common case at free-tier is 429 RESOURCE_EXHAUSTED.
        return True
    if isinstance(exc, genai_errors.ServerError):
        return True
    return False


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def call_gemini(client, *, model: str, contents: list, config) -> Any:
    """Call ``client.models.generate_content`` with automatic retry.

    On 429 errors, if multiple API keys are available, the call is
    retried with a **different key** via ``_rotate_client()``.

    Parameters
    ----------
    client : genai.Client
        The initialised Gemini client (used on first attempt).
    model : str
        Model name, e.g. ``"gemini-3-flash-preview"``.
    contents : list
        Prompt parts (image Part + text).
    config : GenerateContentConfig
        Generation config.

    Returns
    -------
    GenerateContentResponse or None on exhausted retries.
    """
    try:
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    except genai_errors.ClientError:
        # On 429, try switching to a different key before tenacity retries
        if len(_key_pool) > 1:
            alt_client = _rotate_client()
            if alt_client:
                logger.info("Switching to next API key after 429...")
                return alt_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
        raise  # Let tenacity handle the retry


def parse_response(response) -> dict | None:
    """Safely extract parsed JSON from a Gemini response.

    Tries ``response.parsed`` first, then falls back to manual
    ``json.loads(response.text)``.  Returns *None* if both fail.
    """
    if response is None:
        return None

    # Try SDK's built-in parsed attribute
    try:
        result = response.parsed
        if result is not None:
            return result
    except Exception:
        pass

    # Fallback: raw text → json.loads
    try:
        raw = response.text
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    return None
