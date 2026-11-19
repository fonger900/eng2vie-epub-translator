"""Quality check and two-pass refinement for translated text.

After initial translation, scores each output and re-translates
passages below threshold with stricter settings (lower creativity,
smaller batches).

Usage in html_translator.py:
    from .refiner import check_quality, refine_batch
    score, issues = check_quality(original, translated)
    if score < threshold:
        translated = refine(engine, original, ...)
"""

from __future__ import annotations

import re

# ── Quality checks ──────────────────────────────────────────────────────────

# Emphasis tags that must be balanced
_EMPHASIS_TAG_RE = re.compile(r"</?(em|strong|b|i)\b[^>]*>", re.I)

# Minimum acceptable length ratio (translated / original)
_MIN_LENGTH_RATIO = 0.3
_MAX_LENGTH_RATIO = 3.0


def _check_tag_balance(text: str) -> tuple[bool, str]:
    """Check that all emphasis tags open and close correctly."""
    stack: list[str] = []
    for tag_match in _EMPHASIS_TAG_RE.finditer(text):
        raw = tag_match.group(0)
        if raw.startswith("</"):
            name = tag_match.group(1)
            if not stack or stack[-1] != name:
                return False, f"unexpected closing tag </{name}>"
            stack.pop()
        else:
            stack.append(tag_match.group(1))
    if stack:
        return False, f"unclosed tags: {', '.join(stack)}"
    return True, ""


def _check_length_ratio(original: str, translated: str) -> tuple[bool, str]:
    """Check that translated text is not drastically different in length."""
    if not original.strip():
        return True, ""
    ratio = len(translated) / len(original) if len(original) > 0 else 1.0
    if ratio < _MIN_LENGTH_RATIO:
        return False, f"too short ({ratio:.1%})"
    if ratio > _MAX_LENGTH_RATIO:
        return False, f"too long ({ratio:.1%})"
    return True, ""


def check_quality(original: str, translated: str) -> tuple[int, list[str]]:
    """Score translation quality (0-100) and return list of issues.

    Checks:
    - Emphasis tag balance (40 points)
    - Length ratio within bounds (30 points)
    - Non-empty output (30 points)
    """
    issues: list[str] = []
    score = 100

    # Tag balance check
    ok, msg = _check_tag_balance(translated)
    if not ok:
        issues.append(msg)
        score -= 40

    # Length ratio check
    ok, msg = _check_length_ratio(original, translated)
    if not ok:
        issues.append(msg)
        score -= 30

    # Empty output
    if not translated.strip():
        issues.append("empty output")
        score = 0

    return max(score, 0), issues


# ── Refinement loop ────────────────────────────────────────────────────────


def refine_texts(
    originals: list[str],
    translations: list[str],
    engine_cfg,
    threshold: int = 80,
    issues_log: dict[int, list[str]] | None = None,
    **kwargs,
) -> list[str]:
    """Re-translate passages below quality threshold.

    Passages that fail quality check are re-translated one at a time
    (single-element batches) with the same engine. If issues_log is
    provided, it is populated with {index: [issue, ...]} for failed
    passages.

    Returns the refined translation list (same length as originals).
    """
    result = list(translations)  # copy

    for i, (orig, trans) in enumerate(zip(originals, translations)):
        if not orig.strip():
            continue

        score, issues = check_quality(orig, trans)
        if score >= threshold:
            continue

        if issues_log is not None:
            issues_log[i] = issues

        # Retry as single-element batch for cleaner output
        try:
            retry = engine_cfg.translate(
                [orig],
                **kwargs,
            )
            if retry and len(retry) == 1:
                result[i] = retry[0]
        except Exception:
            pass  # Keep original translation on retry failure

    return result
