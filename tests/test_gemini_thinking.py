"""Tests for Gemini thinking-mode configuration."""

from unittest.mock import Mock, patch

import pytest

from trans_epub.engines import gemini


class TestThinkingConfig:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            # 2.5 Flash/Flash-Lite: thinking can be fully disabled.
            ("gemini-2.5-flash", {"thinkingBudget": 0}),
            ("gemini-2.5-flash-lite", {"thinkingBudget": 0}),
            # 2.5 Pro: cannot disable; use the minimum budget.
            ("gemini-2.5-pro", {"thinkingBudget": 128}),
            # 3.x/4.x: use the lowest supported thinking level.
            ("gemini-3.1-flash-lite", {"thinkingLevel": "minimal"}),
            ("gemini-3.5-flash-lite", {"thinkingLevel": "minimal"}),
            ("gemini-3.1-pro", {"thinkingLevel": "low"}),
            ("gemini-3.8-flash", {"thinkingLevel": "low"}),
            ("gemini-4-hydrogen", {"thinkingLevel": "low"}),
            # Models without thinking support must not receive the field.
            ("gemini-1.5-flash", None),
        ],
    )
    def test_model_specific_config(self, model, expected):
        assert gemini._thinking_config(model) == expected


def test_translate_request_has_minimal_thinking(monkeypatch):
    """The default translation request must explicitly minimize thinking."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = {
        "candidates": [
            {
                "content": {"parts": [{"text": '{"translations": ["Xin chào"]}'}]},
                "finishReason": "STOP",
            }
        ]
    }
    resp.raise_for_status.return_value = None

    with patch.object(gemini.http_session, "post", return_value=resp) as post:
        assert gemini.gemini_translate(["Hello"]) == ["Xin chào"]

    payload = post.call_args.kwargs["json"]
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}


def test_thinking_tokens_count_as_output_tokens():
    """Thinking tokens are billed as output, so usage must include them."""
    gemini.reset_gemini_usage()
    try:
        gemini._accumulate_usage(
            {
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 40,
                    "thoughtsTokenCount": 25,
                }
            }
        )
        assert gemini.get_gemini_usage() == (100, 65)
    finally:
        gemini.reset_gemini_usage()
