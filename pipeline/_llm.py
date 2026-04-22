"""
Shared LLM client for the ResearchLens pipeline.
Uses Cerebras Cloud (Llama 3.3 70B).

Free tier: 30 RPM — no daily request cap.
Design: sequential calls with 3s gap (well within 30 RPM = 1 call per 2s).
"""

import os
import re
import json
import time
import logging
import threading
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama-3.3-70b"

_client = None
_client_lock = threading.Lock()

# 30 RPM = 1 call per 2s. We use 3s to be safe.
_call_lock = threading.Lock()
_last_call_time = 0.0
_MIN_CALL_GAP = 3.0   # seconds between consecutive Cerebras calls


def _get_client() -> Cerebras:
    global _client
    with _client_lock:
        if _client is None:
            api_key = os.environ.get("CEREBRAS_API_KEY", "").strip()
            if not api_key or api_key == "your_cerebras_api_key_here":
                raise RuntimeError(
                    "CEREBRAS_API_KEY not set in .env:\n"
                    "  CEREBRAS_API_KEY=csk-..."
                )
            _client = Cerebras(api_key=api_key)
            model = os.environ.get("CEREBRAS_MODEL", _DEFAULT_MODEL)
            logger.info(f"Cerebras ready: {model}  [30 RPM / no daily cap]")
    return _client


def _parse_retry_delay(err: Exception) -> float:
    """Extract retry delay from 429 error, default 10s."""
    try:
        match = re.search(r"retry.?after[\":\s]+(\d+)", str(err), re.IGNORECASE)
        if match:
            return float(match.group(1)) + 2
    except Exception:
        pass
    return 10.0


def _call(prompt: str, json_mode: bool = False) -> str:
    """
    Thread-safe Cerebras call with rate limiting + retry.
    Enforces _MIN_CALL_GAP between consecutive calls.
    """
    global _last_call_time

    model = os.environ.get("CEREBRAS_MODEL", _DEFAULT_MODEL).strip()

    for attempt in range(5):
        with _call_lock:
            # Enforce minimum gap since last call
            elapsed = time.monotonic() - _last_call_time
            if elapsed < _MIN_CALL_GAP and _last_call_time > 0:
                wait = _MIN_CALL_GAP - elapsed
                logger.debug(f"Rate pacing: waiting {wait:.1f}s ...")
                time.sleep(wait)

            try:
                _last_call_time = time.monotonic()
                client = _get_client()

                kwargs = dict(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    max_tokens=8192,
                )
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                resp = client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content

            except Exception as e:
                _last_call_time = time.monotonic()
                err_str = str(e)
                if "429" in err_str or "rate" in err_str.lower() or "quota" in err_str.lower():
                    delay = _parse_retry_delay(e)
                    logger.warning(
                        f"Cerebras 429 (attempt {attempt + 1}/5) — "
                        f"waiting {delay:.0f}s ..."
                    )
                    time.sleep(delay)
                else:
                    logger.warning(f"Cerebras error (attempt {attempt + 1}): {e}")
                    if attempt < 4:
                        time.sleep(3)
                    else:
                        raise

    raise RuntimeError("Cerebras failed after 5 attempts")


def generate_text(prompt: str) -> str:
    """Generate plain text."""
    return _call(prompt, json_mode=False).strip()


def _salvage_truncated_json(raw: str) -> dict | list:
    """
    Try to recover a truncated JSON response from the model.
    Finds the last complete object in an array and closes the structure.
    """
    # Try to close a truncated array: find last '}' and close with ']'
    last_brace = raw.rfind("}")
    if last_brace != -1:
        candidate = raw[: last_brace + 1]
        # If it's inside an array, close the array
        if raw.lstrip().startswith("[") or '"results"' in raw:
            candidate = candidate + "]"
            # Wrap in results if needed
            if '"results"' in raw and not raw.lstrip().startswith("["):
                candidate = '{"results":' + candidate.split('"results":')[-1] if '"results":' in candidate else candidate
        try:
            return json.loads(candidate)
        except Exception:
            pass
    # Last resort: return empty structure
    if raw.lstrip().startswith("["):
        return []
    return {}


def generate_json(prompt: str) -> dict | list:
    """Generate and parse a JSON response. Strips markdown fences if present.
    Falls back to truncation salvage if the response is cut off."""
    raw = _call(prompt, json_mode=True).strip()
    # Strip markdown code fences if model wraps output
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.rstrip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed ({e}) — attempting truncation salvage ...")
        return _salvage_truncated_json(raw)

