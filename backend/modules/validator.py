"""
backend/modules/validator.py
=============================
Validation Module — Phase 2.

Responsibility
--------------
Quality-gate the generated ``SlideSpec`` before it reaches the renderer.
Returns a ``ValidationResult`` that records whether the spec is safe to
render, any issues found, and per-claim quality metadata.

Public API
----------
::

    result: ValidationResult = validate_content(spec)

Design constraints
------------------
- Must NOT call renderers or have Office.js knowledge.
- Must NOT modify the ``SlideSpec`` in place — return a corrected copy
  via ``ValidationResult.validated_spec`` if corrections are needed.
- Must always return a ``ValidationResult``, never raise.
"""

from __future__ import annotations

import json
import logging

from backend.llm.prompt_loader import get_prompt
from backend.presentation_assets import asset_registry
from backend.presentation_assets.manifest_conformance import check_conformance
from backend.presentation_assets.text_fit import check_text_fit, failure_ids
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult

logger = logging.getLogger(__name__)

# Kept loaded for future semantic-validation sprints; structural checks are offline.
VALIDATION_PROMPT = get_prompt("validation")

# Minimum item counts per visual pattern. The layout engine synthesizes an
# adaptive grid from the actual number of items, so fewer-than-canonical items
# are allowed (e.g. 3 real cards instead of 4), but empty placeholders are not.
_PATTERN_MIN_COUNTS: dict[str, int] = {
    "CL-01": 1,
    "CL-02": 1,
    "CL-06": 1,
    "CL-03": 1,
}

# Pattern-native field that must be present (and counted) for each pattern.
_PATTERN_NATIVE_FIELD: dict[str, str] = {
    "CL-01": "cards",
    "CL-02": "cards",
    "CL-06": "cards",
    "CL-03": "kpis",
    "CL-04": "columns",
    "CL-05": "columns",
    "IG-01": "events",
    "IG-02": "phases",
    "IG-03": "steps",
    "IG-04": "cells",
    "IG-05": "stages",
    "IG-06": "domains",
}

# Primary text key to validate per item for each pattern.
_PATTERN_ITEM_TEXT_KEY: dict[str, str] = {
    "CL-01": "title",
    "CL-02": "title",
    "CL-06": "title",
    "CL-03": "label",
    "CL-04": "label",
    "CL-05": "label",
    "IG-01": "label",
    "IG-02": "name",
    "IG-03": "label",
    "IG-04": "value",
    "IG-05": "name",
    "IG-06": "name",
}

_VALID_QUADRANT_VALUES = {"low", "medium", "high"}
_PLACEHOLDER_LEAKAGE_VALUES = {
    "text",
    "title",
    "subtitle",
    "placeholder",
    "lorem ipsum",
    "tbd",
    "n/a",
}


def validate_content(spec: SlideSpec) -> ValidationResult:
    """
    Quality-gate the ``SlideSpec`` before it is passed to the renderer.

    Performs structural checks driven by ``metadata.visual_pattern``:

    - required base keys present (title, subtitle/description, executive_summary)
    - pattern-native field present with the correct item count
    - CL-03 KPIs have non-empty ``value``
    - IG-04 risk cells carry valid quadrant values (Low/Medium/High)
    - no literal ``"unsupported metric"`` anywhere in the spec
    - non-empty title

    On any failure the spec is rejected (``is_valid=False``,
    ``validated_spec=None``) with human-readable ``issues``. Success returns
    the spec unchanged. The validator never raises.
    """
    logger.info(
        "validating spec: slide_type=%s version=%s",
        spec.slide_type,
        spec.version,
    )

    raw = spec.raw_spec if isinstance(spec.raw_spec, dict) else {}
    issues: list[str] = []

    _check_unsupported_metric(raw, issues)
    _check_placeholder_leakage(raw, issues)
    warnings: list[str] = []

    # Sprint D — manifest-aware validation: when an asset was selected, verify
    # the placeholder-keyed raw_spec directly against the asset manifest.
    if spec.asset_id:
        manifest = asset_registry.get(spec.asset_id)
        if manifest is not None:
            issues.extend(check_conformance(raw, manifest))
            fit = check_text_fit(raw, manifest)
            if not fit.passed:
                ids = failure_ids(fit)
                issues.append(
                    "text-fit failed for placeholders: " + ", ".join(ids)
                )
            if issues:
                logger.warning(
                    "validation failed: slide_type=%s asset_id=%s issues=%s",
                    spec.slide_type,
                    spec.asset_id,
                    issues,
                )
                return ValidationResult(
                    is_valid=False, issues=issues, claims=[], validated_spec=None
                )
            return ValidationResult(is_valid=True, issues=warnings, claims=[], validated_spec=spec)

    _check_base_keys(raw, issues)

    metadata = raw.get("metadata", {})
    pattern_id = metadata.get("visual_pattern") if isinstance(metadata, dict) else None

    if pattern_id:
        _check_pattern_native(raw, pattern_id, issues)

    if issues:
        logger.warning("validation failed: slide_type=%s issues=%s", spec.slide_type, issues)
        return ValidationResult(is_valid=False, issues=issues, claims=[], validated_spec=None)

    return ValidationResult(is_valid=True, issues=warnings, claims=[], validated_spec=spec)


def _check_base_keys(raw: dict, issues: list[str]) -> None:
    if not _clean_text(raw.get("title")):
        issues.append("title is missing or empty.")
    if not _clean_text(raw.get("subtitle")) and not _clean_text(raw.get("description")):
        issues.append("subtitle/description is missing or empty.")
    if not _clean_text(raw.get("executive_summary")):
        issues.append("executive_summary is missing or empty.")


def _check_unsupported_metric(raw: dict, issues: list[str]) -> None:
    text = json.dumps(raw, ensure_ascii=False)
    if "unsupported metric" in text:
        issues.append("spec contains a literal 'unsupported metric' placeholder.")


def _check_placeholder_leakage(raw: dict, issues: list[str]) -> None:
    for path, value in _walk_text_values(raw):
        normalized = " ".join(value.strip().lower().split())
        if normalized in _PLACEHOLDER_LEAKAGE_VALUES:
            issues.append(f"placeholder leakage at {path}: {value!r}.")
            continue
        if normalized.startswith("item ") and normalized[5:].isdigit():
            issues.append(f"placeholder leakage at {path}: {value!r}.")
        if normalized.startswith("step ") and normalized[5:].isdigit():
            issues.append(f"placeholder leakage at {path}: {value!r}.")
        if normalized.startswith("phase ") and normalized[6:].isdigit():
            issues.append(f"placeholder leakage at {path}: {value!r}.")


def _walk_text_values(value, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_text_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_text_values(child, f"{path}[{index}]")


def _check_pattern_native(raw: dict, pattern_id: str, issues: list[str]) -> None:
    field = _PATTERN_NATIVE_FIELD.get(pattern_id)
    if field is None:
        return  # unknown pattern — nothing structural to count

    items = raw.get(field)
    if not isinstance(items, list):
        issues.append(f"{pattern_id}: missing native field '{field}'.")
        return

    minimum = _PATTERN_MIN_COUNTS.get(pattern_id, 1)
    if not items:
        issues.append(f"{pattern_id}: '{field}' is empty.")
    elif len(items) < minimum:
        issues.append(f"{pattern_id}: expected at least {minimum} '{field}', found {len(items)}.")

    text_key = _PATTERN_ITEM_TEXT_KEY.get(pattern_id)
    for index, item in enumerate(items):
        if isinstance(item, dict):
            text = _clean_text(item.get(text_key)) if text_key else ""
            if not text:
                issues.append(f"{pattern_id}: {field[:-1]} #{index + 1} has an empty {text_key or 'label'}.")
        elif text_key and not _clean_text(item):
            issues.append(f"{pattern_id}: {field[:-1]} #{index + 1} is empty.")

    if pattern_id == "CL-03":
        for index, kpi in enumerate(items):
            if isinstance(kpi, dict) and not _clean_text(kpi.get("value")):
                issues.append(f"CL-03: kpi #{index + 1} has an empty value.")

    if pattern_id == "IG-04":
        slide_role = raw.get("metadata", {}).get("slide_role", "") if isinstance(raw.get("metadata"), dict) else ""
        if "risk" in str(slide_role).lower():
            _check_risk_quadrants(items, issues)


def _check_risk_quadrants(cells: list, issues: list[str]) -> None:
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        quadrant = cell.get("quadrant")
        if not isinstance(quadrant, dict):
            issues.append(f"IG-04: risk cell #{index + 1} missing quadrant values.")
            continue
        impact = _clean_text(quadrant.get("impact"))
        likelihood = _clean_text(quadrant.get("likelihood"))
        if impact is None or impact.lower() not in _VALID_QUADRANT_VALUES:
            issues.append(f"IG-04: risk cell #{index + 1} has invalid impact '{impact}'.")
        if likelihood is None or likelihood.lower() not in _VALID_QUADRANT_VALUES:
            issues.append(f"IG-04: risk cell #{index + 1} has invalid likelihood '{likelihood}'.")


def _clean_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
