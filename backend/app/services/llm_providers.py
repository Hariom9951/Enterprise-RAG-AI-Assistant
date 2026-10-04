"""
Enterprise RAG AI Assistant — LLM Client Provider
===================================================
Google Gemini API integration for generation, streaming chat, and agent reasoning.
"""

from __future__ import annotations

import abc
import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from loguru import logger

from app.config.settings import settings

GEMINI_QUOTA_EXHAUSTED_MESSAGE = (
    "Gemini usage limit reached. Your retrieved sources are available, "
    "but a new AI response cannot be generated right now. Please try again after the quota resets."
)


class LLMProviderError(Exception):
    """Base exception for LLM provider execution failures."""

    def __init__(
        self,
        message: str,
        is_quota_exhausted: bool = False,
        retry_after: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.is_quota_exhausted = is_quota_exhausted
        self.retry_after = retry_after
        self.status_code = status_code


class LLMQuotaExhaustedError(LLMProviderError):
    """Raised specifically when Gemini daily or account request quota is exhausted."""

    def __init__(
        self,
        message: str = GEMINI_QUOTA_EXHAUSTED_MESSAGE,
        retry_after: float | None = None,
        status_code: int = 429,
    ) -> None:
        super().__init__(
            message=message,
            is_quota_exhausted=True,
            retry_after=retry_after,
            status_code=status_code,
        )


def _extract_retry_delay(
    headers: httpx.Headers | dict[str, str] | None,
    body: str,
    error_obj: dict[str, Any] | None,
) -> float | None:
    if headers:
        hdr_val = headers.get("retry-after") or headers.get("Retry-After")
        if hdr_val:
            try:
                return float(hdr_val.strip())
            except (ValueError, TypeError):
                pass

    if error_obj and isinstance(error_obj, dict):
        details = error_obj.get("details", [])
        if isinstance(details, list):
            for d in details:
                if isinstance(d, dict) and "retryDelay" in d:
                    rd_str = str(d["retryDelay"]).rstrip("s").strip()
                    try:
                        return float(rd_str)
                    except (ValueError, TypeError):
                        pass

    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s?"', body)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, TypeError):
            pass

    return None


def _extract_gemini_error_obj(body: str) -> dict[str, Any] | None:
    try:
        parsed_json: Any = json.loads(body)
        if (
            isinstance(parsed_json, list)
            and len(parsed_json) > 0
            and isinstance(parsed_json[0], dict)
        ):
            first_item: dict[str, Any] = parsed_json[0]
            err = first_item.get("error", first_item)
            if isinstance(err, dict):
                return err
        elif isinstance(parsed_json, dict):
            err = parsed_json.get("error", parsed_json)
            if isinstance(err, dict):
                return err
    except Exception:
        pass
    return None


def _parse_gemini_error(
    status_code: int,
    body: str,
    headers: httpx.Headers | dict[str, str] | None = None,
) -> tuple[bool, float | None, str]:
    """
    Analyzes Gemini HTTP/API error to distinguish quota exhaustion from temporary rate limits.

    Returns:
    --------
    is_quota_exhausted : bool
        True if the daily, billing, or free-tier quota is exhausted. Retries must NOT occur.
        False if this is a transient burst rate limit (RPM/TPM).
    retry_delay_seconds : float | None
        Parsed delay in seconds from 'Retry-After' header or 'retryDelay' detail, if present.
    user_message : str
        Clean, professional user-facing error message without internal stack traces or secrets.
    """
    error_obj = _extract_gemini_error_obj(body)
    retry_delay = _extract_retry_delay(headers, body, error_obj)

    body_lower = body.lower()
    quota_indicators = (
        "quotafailure",
        "generaterequestsperday",
        "requests_per_day",
        "daily request limit",
        "free_tier",
        "exceeded your current quota",
        "check your plan and billing",
        "billing details",
    )
    has_quota_indicator = any(indicator in body_lower for indicator in quota_indicators)

    is_429 = (
        status_code == 429
        or (error_obj and error_obj.get("code") == 429)
        or "resource_exhausted" in body_lower
    )
    is_quota_exhausted = False
    if is_429:
        if has_quota_indicator or (retry_delay is not None and retry_delay > 30.0):
            is_quota_exhausted = True
        elif retry_delay is not None and retry_delay <= 10.0:
            is_quota_exhausted = False
        else:
            is_quota_exhausted = True

    if is_quota_exhausted:
        clean_msg = GEMINI_QUOTA_EXHAUSTED_MESSAGE
    elif status_code == 429:
        clean_msg = "Gemini service rate limit reached. Retrying request..."
    else:
        clean_msg = (
            "Gemini service is temporarily unavailable. Please try again shortly."
        )

    return is_quota_exhausted, retry_delay, clean_msg


class LLMProvider(abc.ABC):
    """
    Abstract Base Class outlining interface contract for LLM provider clients.
    """

    @abc.abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> tuple[str, dict[str, int]]:
        """
        Send prompt parameters to LLM and returns text response + token usage accounting.

        Returns
        -------
        response_text      The generated raw text response.
        token_usage        Dictionary with prompt_tokens, completion_tokens, total_tokens.
        """
        pass

    @abc.abstractmethod
    async def generate_response_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> AsyncGenerator[str, None]:
        """
        Yields text tokens incrementally as they are generated by the LLM.
        """
        yield ""


def _extract_json_objects(buffer: str) -> tuple[list[dict[str, Any]], str]:
    """Parse complete JSON objects from a streaming text buffer."""
    objects: list[dict[str, Any]] = []
    while True:
        start = buffer.find("{")
        if start == -1:
            break

        brace_count = 0
        end = -1
        for i in range(start, len(buffer)):
            if buffer[i] == "{":
                brace_count += 1
            elif buffer[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i
                    break
        if end == -1:
            break

        obj_str = buffer[start : end + 1]
        buffer = buffer[end + 1 :]

        try:
            obj = json.loads(obj_str)
            if isinstance(obj, dict):
                objects.append(obj)
        except Exception:
            pass

    return objects, buffer


def _handle_gemini_generate_error(
    resp: httpx.Response,
    attempt: int,
    max_attempts: int,
) -> float:
    body = resp.text
    res_json: dict[str, Any] = {}
    try:
        res_json = resp.json()
    except Exception:
        pass

    err_code = resp.status_code
    if "error" in res_json and isinstance(res_json["error"], dict):
        err_code = res_json["error"].get("code", resp.status_code)

    is_quota, retry_after, clean_msg = _parse_gemini_error(err_code, body, resp.headers)
    if is_quota:
        logger.error(f"[Gemini] Quota exhausted (code {err_code}). Halting retries.")
        raise LLMQuotaExhaustedError(
            message=clean_msg,
            retry_after=retry_after,
            status_code=429,
        )

    if err_code in (429, 503) and attempt < max_attempts:
        delay = min(
            retry_after if retry_after is not None else (attempt * 2.0),
            10.0,
        )
        logger.warning(
            f"[Gemini] Error {err_code} on attempt {attempt}/{max_attempts}. "
            f"Retrying in {delay:.1f}s..."
        )
        return delay

    if not resp.is_success:
        raise LLMProviderError(
            f"Gemini API returned error HTTP {resp.status_code}",
            status_code=resp.status_code,
        )
    raise LLMProviderError(clean_msg, status_code=err_code)


def _extract_gemini_candidates(res_json: dict[str, Any]) -> tuple[str, dict[str, int]]:
    candidates = res_json.get("candidates", [])
    if not candidates:
        raise LLMProviderError(
            "Gemini API returned empty candidates list (possibly blocked content)."
        )

    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    usage = res_json.get("usageMetadata", {})
    prompt_tokens = usage.get("promptTokenCount", 0)
    completion_tokens = usage.get("candidatesTokenCount", 0)
    total_tokens = usage.get("totalTokenCount", 0)

    token_usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens or (prompt_tokens + completion_tokens),
    }
    return text, token_usage


class GeminiProvider(LLMProvider):
    """
    Client for Google Gemini API via native REST requests.
    Supports single response generation and Server-Sent Events (SSE) streaming.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> tuple[str, dict[str, int]]:
        if not self.api_key:
            raise LLMProviderError(
                "Google Gemini API Key is not configured. "
                "Please set GEMINI_API_KEY in your .env file or environment."
            )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        max_attempts = 3
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.post(url, json=payload)
                    res_json: dict[str, Any] = {}
                    if resp.is_success and "application/json" in resp.headers.get(
                        "content-type", ""
                    ):
                        try:
                            res_json = resp.json()
                        except Exception:
                            pass

                    if not resp.is_success or "error" in res_json:
                        delay = _handle_gemini_generate_error(
                            resp, attempt, max_attempts
                        )
                        await asyncio.sleep(delay)
                        continue

                    return _extract_gemini_candidates(res_json)

                except LLMProviderError:
                    raise
                except httpx.HTTPError as he:
                    if attempt < max_attempts:
                        await asyncio.sleep(attempt * 2.0)
                        continue
                    raise LLMProviderError(
                        f"HTTP request to Gemini failed: {he!s}"
                    ) from he
                except Exception as e:
                    raise LLMProviderError(
                        f"Failed to parse Gemini response: {e!s}"
                    ) from e
            raise LLMProviderError(
                "Gemini API requests failed after maximum retry attempts."
            )

    async def generate_response_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise LLMProviderError(
                "Google Gemini API Key is not configured. "
                "Please set GEMINI_API_KEY in your .env file or environment."
            )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:streamGenerateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        max_stream_attempts = 2
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, max_stream_attempts + 1):
                try:
                    async with client.stream("POST", url, json=payload) as response:
                        if not response.is_success:
                            err_bytes = await response.aread()
                            err_text = err_bytes.decode(errors="replace")
                            is_quota, retry_after, clean_msg = _parse_gemini_error(
                                response.status_code, err_text, response.headers
                            )
                            if is_quota:
                                logger.error(
                                    f"[Gemini Stream] Quota exhausted (HTTP {response.status_code}). Halting retries."
                                )
                                raise LLMQuotaExhaustedError(
                                    message=clean_msg,
                                    retry_after=retry_after,
                                    status_code=response.status_code,
                                )
                            # Transient rate limit with short retry delay
                            if (
                                response.status_code == 429
                                and attempt < max_stream_attempts
                                and retry_after is not None
                                and retry_after <= 5.0
                            ):
                                logger.warning(
                                    f"[Gemini Stream] Transient rate limit. Retrying stream in {retry_after:.1f}s..."
                                )
                                await asyncio.sleep(retry_after)
                                continue

                            raise LLMProviderError(
                                clean_msg
                                if response.status_code == 429
                                else f"Gemini stream failed with HTTP {response.status_code}",
                                is_quota_exhausted=False,
                                retry_after=retry_after,
                                status_code=response.status_code,
                            )

                        buffer = ""
                        async for chunk in response.aiter_text():
                            buffer += chunk
                            objects, buffer = _extract_json_objects(buffer)
                            for obj in objects:
                                for candidate in obj.get("candidates", []):
                                    for part in candidate.get("content", {}).get(
                                        "parts", []
                                    ):
                                        token = part.get("text", "")
                                        if token:
                                            yield token
                        return
                except LLMProviderError:
                    raise
                except httpx.HTTPError as he:
                    if attempt < max_stream_attempts:
                        await asyncio.sleep(1.0)
                        continue
                    raise LLMProviderError(
                        f"HTTP stream request to Gemini failed: {he!s}"
                    ) from he
                except Exception as e:
                    raise LLMProviderError(
                        f"Failed to parse Gemini stream: {e!s}"
                    ) from e


def get_llm_provider(
    provider_name: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """
    Factory function returning the active Google Gemini LLMProvider instance.
    Google Gemini is the sole configured LLM provider for the application.
    """
    if provider_name and provider_name.lower() != "gemini":
        logger.info(
            f"Provider '{provider_name}' requested, routing to sole configured provider 'gemini'."
        )
    return GeminiProvider(api_key=api_key, model=model or settings.gemini_model)
