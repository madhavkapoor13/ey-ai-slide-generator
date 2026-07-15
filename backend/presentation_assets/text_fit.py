"""
backend/presentation_assets/text_fit.py
=======================================
Manifest-driven text-fit checks for Presentation Asset content.

The AI may change content, but it must not resize, restyle, move, or redraw
PowerPoint elements. This module therefore only inspects/shortens strings
against manifest constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemas.presentation_asset import AssetManifest, AssetPlaceholder


@dataclass
class TextFitFailure:
    """One placeholder value that exceeded its declared fit constraints."""

    placeholder_id: str
    reason: str
    index: int | None = None


@dataclass
class TextFitResult:
    """Result of checking or shortening content against a manifest."""

    passed: bool
    failures: list[TextFitFailure] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)
    content: dict[str, Any] | None = None


def check_text_fit(content: dict[str, Any], manifest: AssetManifest) -> TextFitResult:
    """Return fit failures for content values that exceed manifest constraints."""
    failures: list[TextFitFailure] = []
    for placeholder in manifest.placeholders:
        value = content.get(placeholder.id)
        failures.extend(_placeholder_failures(placeholder, value))
    return TextFitResult(passed=not failures, failures=failures, content=content)


def shorten_to_fit_once(content: dict[str, Any], manifest: AssetManifest) -> TextFitResult:
    """
    Try one deterministic content-shortening pass.

    This is the non-LLM implementation of the V2 "regenerate shorter once"
    policy. Placeholders with ``overflow_policy: truncate`` may be truncated;
    all other constrained text is shortened conservatively. If it still fails,
    callers should reject the slide and route to fallback.
    """
    next_content = dict(content)
    truncated: list[str] = []

    for placeholder in manifest.placeholders:
        value = next_content.get(placeholder.id)
        if placeholder.cardinality == "N" and isinstance(value, list):
            next_items: list[Any] = []
            for item in value:
                shortened, changed = _shorten_value(item, placeholder)
                if changed:
                    truncated.append(placeholder.id)
                next_items.append(shortened)
            next_content[placeholder.id] = next_items
        else:
            shortened, changed = _shorten_value(value, placeholder)
            if changed:
                truncated.append(placeholder.id)
            next_content[placeholder.id] = shortened

    checked = check_text_fit(next_content, manifest)
    checked.truncated = sorted(set(truncated))
    checked.content = next_content
    return checked


def failure_ids(result: TextFitResult) -> list[str]:
    """Compact placeholder identifiers for reports and validation issues."""
    ids: list[str] = []
    for failure in result.failures:
        if failure.index is None:
            ids.append(failure.placeholder_id)
        else:
            ids.append(f"{failure.placeholder_id}[{failure.index}]")
    return ids


def _placeholder_failures(placeholder: AssetPlaceholder, value: Any) -> list[TextFitFailure]:
    if value is None:
        return []
    if placeholder.cardinality == "N":
        if not isinstance(value, list):
            return []
        failures: list[TextFitFailure] = []
        for index, item in enumerate(value):
            reason = _fit_reason(_coerce_text(item, placeholder), placeholder)
            if reason:
                failures.append(TextFitFailure(placeholder.id, reason, index=index))
        return failures

    reason = _fit_reason(_coerce_text(value, placeholder), placeholder)
    return [TextFitFailure(placeholder.id, reason)] if reason else []


def _fit_reason(text: str, placeholder: AssetPlaceholder) -> str | None:
    constraints = placeholder.constraints or {}
    max_chars = constraints.get("max_chars")
    max_lines = constraints.get("max_lines")

    if isinstance(max_chars, int) and max_chars > 0 and len(text) > max_chars:
        return f"exceeds max_chars {max_chars}"
    if isinstance(max_lines, int) and max_lines > 0:
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) > max_lines:
            return f"exceeds max_lines {max_lines}"
    return None


def _shorten_value(value: Any, placeholder: AssetPlaceholder) -> tuple[Any, bool]:
    if value is None:
        return value, False
    if isinstance(value, dict):
        changed = False
        next_item: dict[str, Any] = {}
        for key, inner in value.items():
            if isinstance(inner, str):
                shortened, did_change = _shorten_text(inner, placeholder)
                next_item[key] = shortened
                changed = changed or did_change
            else:
                next_item[key] = inner
        return next_item, changed
    if isinstance(value, str):
        return _shorten_text(value, placeholder)
    return value, False


def _shorten_text(text: str, placeholder: AssetPlaceholder) -> tuple[str, bool]:
    constraints = placeholder.constraints or {}
    max_chars = constraints.get("max_chars")
    if not isinstance(max_chars, int) or max_chars <= 0 or len(text) <= max_chars:
        return text, False

    overflow_policy = str(constraints.get("overflow_policy") or "regenerate").lower()
    limit = max(max_chars, 1)
    if overflow_policy == "truncate":
        return text[: max(limit - 1, 0)].rstrip() + ("…" if limit > 1 else ""), True

    words = text.split()
    shortened = ""
    for word in words:
        candidate = f"{shortened} {word}".strip()
        if len(candidate) > limit:
            break
        shortened = candidate
    if shortened:
        return shortened, True
    return text[:limit].rstrip(), True


def _coerce_text(value: Any, placeholder: AssetPlaceholder) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in (placeholder.role, placeholder.id, "title", "label", "name", "text", "description"):
            if key and key in value:
                return str(value[key])
        for inner in value.values():
            if isinstance(inner, (str, int, float)):
                return str(inner)
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)
