"""
backend/layout_engine/layout_registry.py
========================================
Sprint V3 — Layout registry.

Thin lookup layer on top of ``loader.py``. Provides access to loaded layouts
by ID and by the visual pattern they implement.
"""

from __future__ import annotations

from backend.layout_engine.loader import load_layouts
from schemas.layout import LayoutSpecification


def get_layout(layout_id: str) -> LayoutSpecification:
    """
    Return the layout with the given ``layout_id``.

    Raises:
        KeyError: if the layout does not exist.
    """
    layouts = load_layouts()
    return layouts[layout_id]


def list_layouts() -> list[LayoutSpecification]:
    """Return all loaded layouts as a list."""
    return list(load_layouts().values())


def find_by_pattern(pattern_id: str) -> LayoutSpecification | None:
    """
    Return the first layout that implements ``pattern_id``.

    Returns ``None`` if no layout matches the pattern.
    """
    layouts = load_layouts()
    for layout in layouts.values():
        if layout.visual_pattern == pattern_id:
            return layout
    return None
