"""Tests for the OpenRouter engine."""

from unittest.mock import Mock, patch

import pytest

from translator.engines import openrouter
from translator.engines.base import ENGINES

_ENV_VARS = (
    "OPENROUTER_MODEL",
    "OPENROUTER_API_BASE",
    "OPENROUTER_MAX_TOKENS",
    "OPENROUTER_REASONING",
    "OPENROUTER_SITE_URL",
    "OPENROUTER_SITE_NAME",
)


def _response(content: str = '{"translations": ["Xin chào"]}') -> Mock:
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    }
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def no_rate_limit(monkeypatch):
    """Avoid waiting on the shared rate limiter during tests."""
    monkeypatch.setattr(ENGINES["openrouter"], "limiter", None)


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class TestOpenRouterRequest:
    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            openrouter.openrouter_translate(["Hello"])

    def test_default_request(self, clean_env, no_rate_limit):
        with patch.object(
            openrouter.http_session, "post", return_value=_response()
        ) as post:
            assert openrouter.openrouter_translate(["Hello"]) == ["Xin chào"]

        request = post.call_args
        assert request.args[0] == "https://openrouter.ai/api/v1/chat/completions"
        body = request.kwargs["json"]
        assert body["model"] == "google/gemini-3.5-flash-lite"
        assert body["messages"][0]["role"] == "user"
        assert body["response_format"] == {"type": "json_object"}
        assert body["reasoning"] == {"effort": "minimal"}
        assert body["temperature"] == pytest.approx(0.4)
        assert body["max_tokens"] == 8192
        assert request.kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_env_overrides(self, clean_env, no_rate_limit, monkeypatch):
        monkeypatch.setenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
        monkeypatch.setenv("OPENROUTER_API_BASE", "https://example.com/api/v1/")
        monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "4096")
        monkeypatch.setenv("OPENROUTER_REASONING", "none")
        monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
        monkeypatch.setenv("OPENROUTER_SITE_NAME", "Trans EPUB")

        with patch.object(
            openrouter.http_session, "post", return_value=_response()
        ) as post:
            openrouter.openrouter_translate(["Hello"])

        request = post.call_args
        assert request.args[0] == "https://example.com/api/v1/chat/completions"
        assert request.kwargs["json"]["model"] == "deepseek/deepseek-v4-flash"
        assert request.kwargs["json"]["max_tokens"] == 4096
        assert request.kwargs["json"]["reasoning"] == {"effort": "none"}
        headers = request.kwargs["headers"]
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-OpenRouter-Title"] == "Trans EPUB"

    def test_reasoning_default_omits_field(self, clean_env, no_rate_limit, monkeypatch):
        monkeypatch.setenv("OPENROUTER_REASONING", "default")

        with patch.object(
            openrouter.http_session, "post", return_value=_response()
        ) as post:
            openrouter.openrouter_translate(["Hello"])

        assert "reasoning" not in post.call_args.kwargs["json"]

    def test_invalid_reasoning_rejected(self, clean_env, monkeypatch):
        monkeypatch.setenv("OPENROUTER_REASONING", "maximum")

        with patch.object(openrouter.http_session, "post") as post:
            with pytest.raises(ValueError, match="OPENROUTER_REASONING"):
                openrouter.openrouter_translate(["Hello"])

        post.assert_not_called()

    def test_creativity_override(self, clean_env, no_rate_limit):
        with patch.object(
            openrouter.http_session, "post", return_value=_response()
        ) as post:
            openrouter.openrouter_translate(["Hello"], creativity=0.7)

        assert post.call_args.kwargs["json"]["temperature"] == pytest.approx(0.7)
