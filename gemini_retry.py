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
    retry_if_exception,
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
_key_cooldown: dict[int, float] = {}  # key_index → timestamp when usable again


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
    """Get a fresh genai.Client using the next available key.
    Skips keys in cooldown.  Returns None if ALL keys are in cooldown."""
    global _key_index
    if not _key_pool:
        return None
    import time
    now = time.time()
    with _key_lock:
        for _ in range(len(_key_pool)):
            idx = _key_index % len(_key_pool)
            _key_index = (_key_index + 1) % len(_key_pool)
            cooldown_until = _key_cooldown.get(idx, 0)
            if now >= cooldown_until:
                logger.info(f"Using API key #{idx + 1}")
                return genai.Client(api_key=_key_pool[idx])
    # ALL keys are in cooldown — return None so caller can handle
    return None


def _mark_key_exhausted(key: str, cooldown_secs: float = 62.0):
    """Mark a key as exhausted so it's skipped for `cooldown_secs`."""
    import time
    try:
        idx = _key_pool.index(key)
        with _key_lock:
            _key_cooldown[idx] = time.time() + cooldown_secs
            logger.warning(f"Key #{idx + 1} marked exhausted, cooldown {cooldown_secs}s")
    except ValueError:
        pass


def get_quota_wait_seconds() -> float:
    """Return seconds until the earliest key exits cooldown (0 if a key is available now)."""
    import time
    if not _key_pool:
        return 0
    now = time.time()
    with _key_lock:
        for idx in range(len(_key_pool)):
            if now >= _key_cooldown.get(idx, 0):
                return 0  # at least one key is available
        # All in cooldown — find the shortest remaining wait
        earliest = min(_key_cooldown.values())
        return max(0, earliest - now)

# Retry on ClientError (429 rate-limit) and ServerError (5xx transient)
_RETRYABLE = (genai_errors.ClientError, genai_errors.ServerError)


def _is_retryable(exc: BaseException) -> bool:
    """Only retry on rate-limit (429) or transient server errors.
    Do NOT retry 400 INVALID_ARGUMENT — those are permanent failures."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        err_str = str(exc)
        # Only retry quota/rate-limit errors
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            return True
        # Don't retry 400, 403, etc. — they're not transient
        return False
    return False


class QuotaExhaustedError(Exception):
    """Raised when ALL API keys are rate-limited and need a cooldown wait."""
    def __init__(self, wait_seconds: float):
        self.wait_seconds = wait_seconds
        super().__init__(f"All API keys exhausted. Retry in {wait_seconds:.0f}s")


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def call_gemini(client, *, model: str, contents: list, config) -> Any:
    """Call ``client.models.generate_content`` with automatic retry.

    Fast retries with key rotation only (max ~30s total).
    If ALL keys are exhausted raises QuotaExhaustedError so the caller
    can emit SSE progress events during the cooldown wait.

    Parameters
    ----------
    client : genai.Client
        The initialised Gemini client (used on first attempt).
    model, contents, config : standard Gemini args.

    Returns
    -------
    GenerateContentResponse

    Raises
    ------
    QuotaExhaustedError
        When all keys are in cooldown.
    """
    try:
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    except genai_errors.ClientError as e:
        err_str = str(e)
        is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

        if is_quota and _key_pool:
            # Mark the key that just failed
            with _key_lock:
                exhausted_idx = (_key_index - 1) % len(_key_pool)
            _mark_key_exhausted(_key_pool[exhausted_idx])

        # Try a different key immediately
        alt_client = _rotate_client()
        if alt_client:
            logger.info("Switching to next API key after rate-limit...")
            try:
                return alt_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except genai_errors.ClientError:
                pass  # fall through

        # If all keys exhausted, raise special error (don't block here)
        if is_quota:
            wait = get_quota_wait_seconds()
            raise QuotaExhaustedError(wait) from e

        raise  # non-quota error → let tenacity retry


async def call_gemini_async(client, *, model: str, contents: list, config) -> Any:
    """Non-blocking wrapper for the synchronous Gemini API call.

    Pushes the network-bound ``call_gemini`` to a background thread
    so FastAPI's event loop stays responsive during the 3-8 second
    API round-trip.
    """
    return await asyncio.to_thread(
        call_gemini, client, model=model, contents=contents, config=config,
    )


async def call_gemini_with_quota_retry(
    client,
    *,
    model: str,
    contents: list,
    config,
    sse_callback=None,
    max_quota_retries: int = 3,
) -> Any:
    """Gemini call with automatic quota-wait + SSE progress feedback.

    When all API keys are exhausted, this function:
    1. Emits an SSE countdown event every 5 seconds so the UI shows progress
    2. Waits for the cooldown to expire
    3. Retries the call with a refreshed key

    Parameters
    ----------
    sse_callback : async callable(dict), optional
        Called with SSE event dicts during quota waits so the frontend
        can display a countdown (e.g. "Waiting 45s for quota reset...").
    max_quota_retries : int
        How many times to wait-and-retry on quota exhaustion (default: 3).
    """
    for attempt in range(max_quota_retries + 1):
        try:
            return await call_gemini_async(
                client, model=model, contents=contents, config=config,
            )
        except QuotaExhaustedError as qe:
            if attempt >= max_quota_retries:
                raise  # give up after max retries

            wait_secs = max(qe.wait_seconds, 15)  # at least 15s
            logger.warning(f"Quota exhausted (attempt {attempt + 1}). "
                           f"Waiting {wait_secs:.0f}s...")

            # Emit countdown events every 5 seconds
            remaining = wait_secs
            while remaining > 0:
                if sse_callback:
                    await sse_callback({
                        "icon": "⏳",
                        "text": f"API quota reached — waiting {int(remaining)}s for reset… (attempt {attempt + 2}/{max_quota_retries + 1})",
                        "phase": "quota_wait",
                    })
                await asyncio.sleep(min(5, remaining))
                remaining -= 5

            # Rotate to a fresh client after cooldown
            refreshed = _rotate_client()
            if refreshed:
                client = refreshed

            if sse_callback:
                await sse_callback({
                    "icon": "🔄",
                    "text": "Retrying API call…",
                    "phase": "quota_retry",
                })


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
