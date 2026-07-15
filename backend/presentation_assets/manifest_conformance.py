"""
backend/presentation_assets/manifest_conformance.py
====================================================
Manifest conformance — checks a content dict (``SlideSpec.raw_spec`` keyed
by manifest placeholder ids) against an :class:`AssetManifest`.

Used by the validator (Sprint D) to ensure the Content Generator emitted
exactly what the asset's placeholders expect: required placeholders are
present, repeating cardinalities stay within ``density_range``, and
``content_schema`` is structurally satisfied.

Returns a list of human-readable issue strings; an empty list means the
content conforms.

Kept deliberately lightweight: deep runtime schema validation is overkill
for the MVP and expensive at deck-generation time. We check the contract
that the Populator depends on (every required slot non-empty, cardinalities
honoured, structured-shape fields present) — no recursive typing.
"""

from __future__ import annotations

from typing import Any

from schemas.presentation_asset import AssetManifest


def check_conformance(content: dict[str, Any], manifest: AssetManifest) -> list[str]:
    """
    Validate ``content`` against ``manifest``.

    Returns a list of human-readable issue strings. Empty list = conforms.
    """
    issues: list[str] = []
    manifest_ids = {ph.id for ph in manifest.placeholders}

    for ph in manifest.placeholders:
        if ph.cardinality == "1":
            if ph.required:
                value = content.get(ph.id)
                if value is None or value == "" or value == []:
                    issues.append(
                        f"required placeholder {ph.id!r} is missing or empty"
                    )
        elif ph.cardinality == "N":
            value = content.get(ph.id)
            if value is None:
                if ph.required:
                    issues.append(
                        f"required repeating placeholder {ph.id!r} is missing"
                    )
                continue
            if not isinstance(value, list):
                issues.append(
                    f"repeating placeholder {ph.id!r} must be a list, got {type(value).__name__}"
                )
                continue
            lo, hi = manifest.density_range
            if len(value) > hi:
                issues.append(
                    f"placeholder {ph.id!r} has {len(value)} items; exceeds density max {hi}"
                )
            if ph.required and len(value) < lo:
                issues.append(
                    f"required placeholder {ph.id!r} has {len(value)} items; below density min {lo}"
                )
            if ph.content_schema:
                for i, item in enumerate(value):
                    issue = _check_structured(item, ph.id, i, ph.content_schema)
                    if issue:
                        issues.append(issue)

    extras = [k for k in content.keys() if k not in manifest_ids]
    if extras:
        issues.append(f"content has keys not declared in manifest: {extras}")

    return issues


def _check_structured(
    item: Any, placeholder_id: str, idx: int, schema: dict[str, Any]
) -> str | None:
    """
    Lightweight per-item structural check against a ``content_schema``.

    ``schema`` is a dict like ``{"label": "string", "owner": "string?",
    "deliverables": "string[]?"}`` where ``?`` suffix marks an optional
    field. Returns an issue string or ``None`` if the item conforms.
    """
    if not isinstance(item, dict):
        return (
            f"placeholder {placeholder_id!r}[{idx}] must be an object "
            f"matching content_schema, got {type(item).__name__}"
        )

    for raw_key, raw_kind in schema.items():
        optional = str(raw_kind).endswith("?")
        expected = str(raw_kind).rstrip("?")
        clean_key = raw_key[:-1] if raw_key.endswith("?") else raw_key

        if clean_key not in item:
            if not optional:
                return (
                    f"placeholder {placeholder_id!r}[{idx}] missing required "
                    f"content field {clean_key!r}"
                )
            continue

        value = item[clean_key]
        if expected == "string" and not isinstance(value, str):
            return (
                f"placeholder {placeholder_id!r}[{idx}] field {clean_key!r} "
                f"must be string, got {type(value).__name__}"
            )
        if expected == "string[]" and not isinstance(value, list):
            return (
                f"placeholder {placeholder_id!r}[{idx}] field {clean_key!r} "
                f"must be string[], got {type(value).__name__}"
            )

    return None