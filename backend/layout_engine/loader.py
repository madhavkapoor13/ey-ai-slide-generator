"""
backend/layout_engine/loader.py
===============================
Sprint V3 — Layout loader.

Loads normalized layout JSON files from ``backend/layouts/``, validates them
against ``LayoutSpecification``, and caches the result.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from schemas.layout import LayoutSpecification

logger = logging.getLogger(__name__)

_LAYOUTS_DIR = Path(__file__).resolve().parents[1] / "layouts"

_layout_cache: dict[str, LayoutSpecification] | None = None


def _load_layout_file(path: Path) -> LayoutSpecification:
    """Load and validate a single layout JSON file."""
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return LayoutSpecification.model_validate(data)


def load_layouts() -> dict[str, LayoutSpecification]:
    """
    Load all layout JSON files under ``backend/layouts/``.

    The result is cached after the first call. Returns a mapping of
    ``layout_id`` to ``LayoutSpecification``.
    """
    global _layout_cache

    if _layout_cache is not None:
        return _layout_cache

    if not _LAYOUTS_DIR.exists():
        raise FileNotFoundError(f"Layouts directory not found: {_LAYOUTS_DIR}")

    layouts: dict[str, LayoutSpecification] = {}
    for path in sorted(_LAYOUTS_DIR.rglob("*.json")):
        try:
            layout = _load_layout_file(path)
        except Exception as exc:
            logger.warning("Skipping invalid layout file %s: %s", path, exc)
            continue

        if layout.layout_id in layouts:
            raise ValueError(
                f"Duplicate layout_id '{layout.layout_id}' found in {path}"
            )
        layouts[layout.layout_id] = layout

    logger.info("layout_engine.loader: loaded %d layouts", len(layouts))
    _layout_cache = layouts
    return _layout_cache


def clear_cache() -> None:
    """Clear the cached layouts. Useful for tests."""
    global _layout_cache
    _layout_cache = None
