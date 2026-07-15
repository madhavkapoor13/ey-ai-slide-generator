"""
backend/design_system/design_language.py
======================================
Sprint I5 — Design Language Extraction Engine.

Loads reusable consulting design rules from ``backend/design_language/`` and
exposes renderer-friendly accessors. The engine is template-aware only as
reference material: it reads optional ``design_metadata`` from the visual
pattern registry, but it never loads or populates PowerPoint templates.

Lookup precedence:
1. Pattern-specific override from ``creative_listings.json`` / ``infographics.json``.
2. Optional ``design_metadata`` embedded in ``backend/visual_patterns/*.json``.
3. Generic rule files (``spacing.json``, ``alignment.json``, ``hierarchy.json``,
   ``emphasis.json``, ``visual_rules.json``).
4. Sensible default fallback.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DESIGN_LANGUAGE_DIR = Path(__file__).resolve().parents[1] / "design_language"
_VISUAL_PATTERNS_DIR = Path(__file__).resolve().parents[1] / "visual_patterns"

_default_rules: dict[str, Any] | None = None
_pattern_rules: dict[str, dict[str, Any]] | None = None
_pattern_metadata: dict[str, dict[str, Any]] | None = None
_initialized = False

_MISSING = object()


def _load_json(path: Path) -> Any:
    """Load a JSON file, returning an empty structure on failure."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load design language file %s: %s", path, exc)
        return {}


def _initialize() -> None:
    """Load all design language JSON files once."""
    global _default_rules, _pattern_rules, _pattern_metadata, _initialized
    if _initialized:
        return

    _default_rules = {
        "spacing": _load_json(_DESIGN_LANGUAGE_DIR / "spacing.json"),
        "alignment": _load_json(_DESIGN_LANGUAGE_DIR / "alignment.json"),
        "hierarchy": _load_json(_DESIGN_LANGUAGE_DIR / "hierarchy.json"),
        "emphasis": _load_json(_DESIGN_LANGUAGE_DIR / "emphasis.json"),
        "visual_rules": _load_json(_DESIGN_LANGUAGE_DIR / "visual_rules.json"),
    }

    creative = _load_json(_DESIGN_LANGUAGE_DIR / "creative_listings.json")
    infographics = _load_json(_DESIGN_LANGUAGE_DIR / "infographics.json")

    _pattern_rules = {}
    if isinstance(creative, dict):
        _pattern_rules.update(creative)
    if isinstance(infographics, dict):
        _pattern_rules.update(infographics)

    # Also ingest optional design_metadata from the visual pattern registry.
    _pattern_metadata = {}
    for file_name in ("creative_patterns.json", "infographic_patterns.json"):
        data = _load_json(_VISUAL_PATTERNS_DIR / file_name)
        if not isinstance(data, list):
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            pattern_id = entry.get("pattern_id")
            meta = entry.get("design_metadata")
            if pattern_id and isinstance(meta, dict):
                _pattern_metadata[pattern_id] = meta

    _initialized = True


def _lookup(
    category: str,
    context: str,
    key: str | None,
    pattern_id: str | None,
) -> Any:
    """
    Search a single category for ``context[.key]`` with pattern overrides.

    Returns ``_MISSING`` when nothing is found so the caller can continue
    searching other categories or fall back.
    """
    # Pattern-specific override from design_language/*.json
    if pattern_id and _pattern_rules and pattern_id in _pattern_rules:
        cat_rules = _pattern_rules[pattern_id].get(category, {})
        value = _resolve(cat_rules, context, key)
        if value is not _MISSING:
            return value

    # Optional design_metadata from visual_patterns/*.json
    if pattern_id and _pattern_metadata and pattern_id in _pattern_metadata:
        cat_rules = _pattern_metadata[pattern_id].get(category, {})
        value = _resolve(cat_rules, context, key)
        if value is not _MISSING:
            return value

    # Generic default rules
    cat_rules = _default_rules.get(category, {}) if _default_rules else {}
    return _resolve(cat_rules, context, key)


def _resolve(rules: Any, context: str, key: str | None) -> Any:
    """Resolve ``context[.key]`` inside a rule dictionary."""
    if not isinstance(rules, dict):
        return _MISSING
    context_value = rules.get(context, _MISSING)
    if context_value is _MISSING:
        return _MISSING
    if key is None:
        return context_value
    if isinstance(context_value, dict):
        return context_value.get(key, _MISSING)
    return _MISSING


def get(
    context: str,
    key: str | None = None,
    *,
    pattern_id: str | None = None,
    category: str | None = None,
    default: Any = None,
) -> Any:
    """
    Generic design-language lookup.

    Parameters
    ----------
    context:
        Logical context, e.g. ``"card"``, ``"timeline"``, ``"matrix"``,
        ``"primary"``, ``"card_title"``.
    key:
        Optional specific key inside the context block, e.g. ``"padding"``.
    pattern_id:
        Optional visual pattern ID for pattern-specific overrides.
    category:
        Optional category to search (``"spacing"``, ``"alignment"``,
        ``"hierarchy"``, ``"emphasis"``, ``"visual_rules"``). When omitted,
        all categories are searched in that order.
    default:
        Value returned when no rule is found.

    Returns
    -------
    The resolved rule value or ``default``.
    """
    _initialize()

    if category:
        value = _lookup(category, context, key, pattern_id)
        return default if value is _MISSING else value

    for cat in ("spacing", "alignment", "hierarchy", "emphasis", "visual_rules"):
        value = _lookup(cat, context, key, pattern_id)
        if value is not _MISSING:
            return value

    return default


def get_card_spacing(pattern_id: str | None = None) -> dict[str, Any]:
    """Return card spacing rules as a dict."""
    return {
        "padding": get("card", "padding", pattern_id=pattern_id, category="spacing", default=0.12),
        "gap": get("card", "gap", pattern_id=pattern_id, category="spacing", default=0.10),
        "border_width": get("card", "border_width", pattern_id=pattern_id, category="spacing", default=0.011111),
    }


def get_header_spacing(pattern_id: str | None = None) -> dict[str, Any]:
    """Return header spacing rules as a dict."""
    return {
        "height": get("header", "height", pattern_id=pattern_id, category="spacing", default=0.15),
        "title_height": get("header", "title_height", pattern_id=pattern_id, category="spacing", default=0.06),
        "subtitle_height": get("header", "subtitle_height", pattern_id=pattern_id, category="spacing", default=0.04),
        "margin_bottom": get("header", "margin_bottom", pattern_id=pattern_id, category="spacing", default=0.03),
    }


def get_footer_spacing(pattern_id: str | None = None) -> dict[str, Any]:
    """Return footer spacing rules as a dict."""
    return {
        "height": get("footer", "height", pattern_id=pattern_id, category="spacing", default=0.10),
        "note_height": get("footer", "note_height", pattern_id=pattern_id, category="spacing", default=0.05),
        "margin_top": get("footer", "margin_top", pattern_id=pattern_id, category="spacing", default=0.03),
    }


def get_alignment(context: str, pattern_id: str | None = None) -> str:
    """Return the preferred alignment for a context."""
    value = get(context, "preferred", pattern_id=pattern_id, category="alignment", default=_MISSING)
    if value is _MISSING:
        value = get(context, "default", pattern_id=pattern_id, category="alignment", default="left")
    return str(value)


def get_margin(context: str, pattern_id: str | None = None) -> float:
    """Return a margin value (in inches) for a context."""
    return get(context, None, pattern_id=pattern_id, category="spacing", default=0.10)


def get_emphasis(level: str, pattern_id: str | None = None) -> dict[str, Any]:
    """Return emphasis rules for a level (primary, secondary, accent, muted)."""
    value = get(level, None, pattern_id=pattern_id, category="emphasis")
    if isinstance(value, dict):
        return value
    return {"bold": False, "color_role": "ink"}


def get_typography_hierarchy(role: str, pattern_id: str | None = None) -> dict[str, Any]:
    """Return typography hierarchy rules for a role."""
    value = get(role, None, pattern_id=pattern_id, category="hierarchy")
    if isinstance(value, dict):
        return value
    return {"font": "body", "size": 10.5, "bold": False}


def get_whitespace(context: str = "whitespace", pattern_id: str | None = None) -> dict[str, Any]:
    """Return whitespace rules for a context."""
    value = get(context, None, pattern_id=pattern_id, category="visual_rules")
    if isinstance(value, dict):
        return value
    return {}


def clear_cache() -> None:
    """Clear cached design language rules. Useful for tests."""
    global _default_rules, _pattern_rules, _pattern_metadata, _initialized
    _default_rules = None
    _pattern_rules = None
    _pattern_metadata = None
    _initialized = False
