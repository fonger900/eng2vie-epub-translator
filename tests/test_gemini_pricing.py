"""Tests for Gemini model pricing lookups."""

import pytest

from trans_epub.engines import gemini


class TestResolvePricing:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("gemini-3.5-flash-lite", (0.30, 2.50)),
            ("gemini-3.1-flash-lite", (0.25, 1.50)),
            ("gemini-2.5-flash-lite", (0.10, 0.40)),
            ("gemini-3.5-flash", (1.50, 9.00)),
        ],
    )
    def test_exact_and_prefix_models(self, model, expected):
        assert gemini._resolve_pricing(model) == expected

    def test_flash_lite_does_not_fall_back_to_flash(self):
        """Regression: 3.5 Flash-Lite must not use 3.5 Flash prices."""
        assert gemini._resolve_pricing("gemini-3.5-flash-lite") != (1.50, 9.00)
