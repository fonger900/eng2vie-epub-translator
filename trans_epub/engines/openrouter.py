"""OpenRouter translation engine.

OpenRouter provides one API for many models from different providers.

Set OPENROUTER_API_KEY in your .env file.
Optionally set OPENROUTER_MODEL to override the model name
(default: google/gemini-3.5-flash-lite).
Optionally set OPENROUTER_MAX_TOKENS to override max output tokens (default: 8192).
Optionally set OPENROUTER_API_BASE to override the API endpoint.
Optionally set OPENROUTER_REASONING to control thinking tokens:
  none, minimal, low, medium, high, xhigh, max, or "default" to omit the field.
  Defaults to "minimal" to save output tokens on reasoning models.
Optionally set OPENROUTER_SITE_URL and OPENROUTER_SITE_NAME for app attribution.

Model IDs use the provider prefix, e.g. "google/gemini-3.5-flash-lite",
"deepseek/deepseek-v4-flash", or "openrouter/free". Browse available models at
https://openrouter.ai/models.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import requests

from .base import (
    ENGINES,
    EngineConfig,
    build_prompt,
    call_with_retry,
    extract_translations,
    http_session,
)

if TYPE_CHECKING:
    from ..config import Glossary

DEFAULT_OPENROUTER_CREATIVITY = 0.4
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "google/gemini-3.5-flash-lite"
_DEFAULT_MAX_TOKENS = 8192
_DEFAULT_REASONING = "minimal"
_VALID_REASONING = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


def _reasoning_config() -> dict[str, str] | None:
    """Build OpenRouter's unified reasoning config from the environment."""
    value = os.environ.get("OPENROUTER_REASONING", _DEFAULT_REASONING).strip().lower()
    if value in ("", "default"):
        return None
    if value == "off":
        value = "none"
    if value not in _VALID_REASONING:
        allowed = ", ".join(sorted(_VALID_REASONING | {"default"}))
        raise ValueError(f"OPENROUTER_REASONING must be one of: {allowed}")
    return {"effort": value}


def _headers(key: str) -> dict[str, str]:
    """Build request headers, including optional OpenRouter attribution."""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if site_url := os.environ.get("OPENROUTER_SITE_URL"):
        headers["HTTP-Referer"] = site_url
    if site_name := os.environ.get("OPENROUTER_SITE_NAME"):
        headers["X-OpenRouter-Title"] = site_name
    return headers


def openrouter_translate(
    texts: list[str],
    creativity: float | None = None,
    glossary: Glossary | None = None,
    extra_prompt: str = "",
) -> list[str]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not found in environment")

    base_url = (os.environ.get("OPENROUTER_API_BASE") or _DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("OPENROUTER_MODEL") or _DEFAULT_MODEL
    max_tokens = int(os.environ.get("OPENROUTER_MAX_TOKENS", _DEFAULT_MAX_TOKENS))
    temperature = DEFAULT_OPENROUTER_CREATIVITY if creativity is None else creativity

    prompt = build_prompt(glossary, extra_prompt) + json.dumps(
        {"texts": texts}, ensure_ascii=False
    )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if reasoning := _reasoning_config():
        payload["reasoning"] = reasoning

    def do_request():
        return http_session.post(
            f"{base_url}/chat/completions",
            headers=_headers(key),
            json=payload,
            timeout=120,
        )

    def parse(resp: requests.Response) -> list[str]:
        choice = resp.json()["choices"][0]
        raw = choice["message"].get("content")
        if not raw:
            raise ValueError(
                f"OpenRouter returned empty content "
                f"(finish_reason={choice.get('finish_reason')})"
            )
        return extract_translations(raw)

    return call_with_retry(
        "OpenRouter", do_request, parse, limiter=ENGINES["openrouter"].limiter
    )


ENGINES["openrouter"] = EngineConfig(
    name="openrouter",
    translate=openrouter_translate,
    char_limit=10_000,
    elem_limit=25,
    delay=0,
)
