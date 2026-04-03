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

import time

class AuraGradeKeyManager:
    def __init__(self, api_keys):
        self.key_pool = [{"key": k, "active": True, "retry_at": 0, "fail_count": 0} for k in api_keys]
        self.current_index = 0
        self.lock = threading.Lock()
        self.last_used_key = None  # Track the key that was last used

    def get_working_key(self):
        now = time.time()
        with self.lock:
            # Refresh any keys whose cooldown has expired
            for item in self.key_pool:
                if not item["active"] and now > item["retry_at"]:
                    item["active"] = True
                    item["fail_count"] = 0  # Reset fail count on cooldown expiry
            
            # Find the next active key (round-robin)
            for _ in range(len(self.key_pool)):
                item = self.key_pool[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.key_pool)
                if item["active"]:
                    self.last_used_key = item["key"]
                    return item
            
            return None  # All keys exhausted

    def get_last_used_key(self) -> str | None:
        """Return the key that was most recently used."""
        return self.last_used_key

    def mark_exhausted(self, key, cooldown_secs=30.0):
        """Mark a key as exhausted with shorter cooldown (30s default since we have many keys)."""
        with self.lock:
            for item in self.key_pool:
                if item["key"] == key:
                    item["active"] = False
                    item["fail_count"] += 1
                    # Increase cooldown for keys that fail repeatedly
                    actual_cooldown = cooldown_secs * min(item["fail_count"], 3)
                    item["retry_at"] = time.time() + actual_cooldown
                    logger.warning(f"Key {key[:8]}... marked exhausted (fail #{item['fail_count']}), cooldown {actual_cooldown}s")
                    break

    def get_active_key_count(self) -> int:
        """Return how many keys are currently active."""
        now = time.time()
        with self.lock:
            return sum(1 for item in self.key_pool if item["active"] or now >= item["retry_at"])

    def get_quota_wait_seconds(self) -> float:
        now = time.time()
        with self.lock:
            if not self.key_pool: return 0
            for item in self.key_pool:
                if item["active"] or now >= item["retry_at"]:
                    return 0
            earliest = min(item["retry_at"] for item in self.key_pool)
            return max(0, earliest - now)

_key_manager = None
_key_pool = []  # Expose for backward-compatibility

def init_key_pool():
    """Build the key pool from environment variables (or array) on startup."""
    global _key_manager, _key_pool
    keys = []
    primary = os.environ.get("GEMINI_API_KEY", "")
    if primary:
        keys.append(primary)

    # Optional comma-separated key list for easier deployment configuration.
    # Example: GEMINI_API_KEYS="keyA,keyB,keyC"
    key_list = os.environ.get("GEMINI_API_KEYS", "")
    if key_list:
        for item in key_list.split(","):
            key = item.strip()
            if key and key not in keys:
                keys.append(key)

    for i in range(2, 10):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "")
        if k and k not in keys:
            keys.append(k)

    if not keys:
        logger.warning("No Gemini API keys configured. Set GEMINI_API_KEY or GEMINI_API_KEYS.")

    _key_manager = AuraGradeKeyManager(keys)
    _key_pool = keys
    if len(keys) > 1:
        print(f"SUCCESS: Gemini key pool: {len(keys)} keys loaded (AuraGradeKeyManager failover enabled)")
    elif len(keys) == 1:
        print("SUCCESS: Gemini key pool: 1 key loaded")

def _rotate_client():
    if not _key_manager or not _key_pool:
        return None
    key_item = _key_manager.get_working_key()
    if key_item:
        logger.info(f"Using API key {key_item['key'][:8]}...")
        return genai.Client(api_key=key_item["key"])
    return None

def _mark_key_exhausted(key: str, cooldown_secs: float = 30.0):
    """Mark a key as exhausted. Shorter cooldown (30s) since we have multiple keys."""
    if _key_manager:
        _key_manager.mark_exhausted(key, cooldown_secs)

def get_quota_wait_seconds() -> float:
    if not _key_manager:
        return 0
    return _key_manager.get_quota_wait_seconds()

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
    # Track which key we're using for proper exhaustion marking
    current_key = _key_manager.get_last_used_key() if _key_manager else None
    
    try:
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    except genai_errors.ClientError as e:
        err_str = str(e)
        is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

        if is_quota and _key_manager:
            # Mark the key that just failed using our tracking
            if current_key:
                _mark_key_exhausted(current_key)
            
            # Try ALL remaining active keys before giving up
            max_key_attempts = len(_key_pool) if _key_pool else 0
            for attempt in range(max_key_attempts):
                alt_client = _rotate_client()
                if not alt_client:
                    break  # No more active keys
                
                new_key = _key_manager.get_last_used_key()
                logger.info(f"Switching to API key {new_key[:8] if new_key else '?'}... (attempt {attempt + 2}/{max_key_attempts + 1})")
                
                try:
                    return alt_client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                except genai_errors.ClientError as retry_exc:
                    retry_err = str(retry_exc)
                    if "429" in retry_err or "RESOURCE_EXHAUSTED" in retry_err:
                        # This key is also exhausted, mark it and try next
                        if new_key:
                            _mark_key_exhausted(new_key)
                        continue
                    else:
                        # Non-quota error, re-raise
                        raise

            # All keys exhausted, raise special error
            wait = get_quota_wait_seconds()
            active_count = _key_manager.get_active_key_count() if _key_manager else 0
            logger.error(f"All {len(_key_pool)} API keys exhausted. Active: {active_count}. Wait: {wait}s")
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
                        "icon": "WAIT",
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
                    "icon": "RETRY",
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
